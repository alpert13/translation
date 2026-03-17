import os
import time
import uuid
from typing import List, Dict
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# Import từ các file local
from config import sequential_config, deepseek_config, coi_config, batch_config,coi_deepseek_config
from data import load_chapters
from make_book import create_epub_from_txt, extract_number
from main import get_provider
from translator import TranslatorCore

app = FastAPI(title="LOTM Translation API", description="API server for novel translation system")

# In-memory database để lưu trạng thái của các job dịch
JOBS: Dict[str, dict] = {}

# Dictionary để map tên config với biến config thực tế từ config.py
CONFIG_MAP = {
    "sequential_config": sequential_config,
    "deepseek_config": deepseek_config,
    "coi_config": coi_config,
    "batch_config": batch_config,
    "coi_deepseek_config":coi_deepseek_config
}

# --- MODELS ---
class TranslateRequest(BaseModel):
    start_chapter: int
    end_chapter: int
    config_name: str = "sequential_config"

# --- WORKER FUNCTIONS ---
def translation_worker(job_id: str, req_start: int, req_end: int, to_translate: List[int], cfg: dict):
    """Hàm chạy nền (background task) để dịch tuần tự hoặc batch."""
    
    JOBS[job_id]["status"] = "running"
    
    try:
        # 1. Khởi tạo Provider & TranslatorCore y hệt như main.py
        provider = get_provider(cfg)
        translator = TranslatorCore(cfg, provider)
        
        # Override start và end chapter dựa theo request của API
        translator.start_chapter = req_start
        translator.end_chapter = req_end
        
        # 2. Xử lý Dịch
        if cfg.get("use_batch_mode") and provider.supports_batch():
            JOBS[job_id]["status"] = "running_batch"
            
            # Delegate mọi thứ cho translator core (hỗ trợ update từ điển)
            translator.run_batch_loop()
            
            JOBS[job_id]["completed"] = len(to_translate)
            JOBS[job_id]["status"] = "completed"
            
        else:
            # Sequential mode với tracking tiến trình cho API
            pickle_file = cfg.get("pickle_file", "./text.pkl")
            chapters = load_chapters(pickle_file)
            chapter_dict = {ch['chapter_id']: ch for ch in chapters}
            
            for cid in to_translate:
                if JOBS[job_id]["status"] == "cancelled":
                    break
                    
                JOBS[job_id]["current_chapter"] = cid
                
                if cid not in chapter_dict:
                    JOBS[job_id]["errors"].append(f"Không tìm thấy chương {cid} trong file dữ liệu.")
                    JOBS[job_id]["completed"] += 1
                    continue
                    
                ch = chapter_dict[cid]
                try:
                    # Dùng TranslatorCore để dịch và lưu (bao gồm build prompt, học từ, save file format chuẩn)
                    translation_raw = translator.translate_chapter_once(ch)
                    translator.process_and_save_translation(cid, translation_raw)
                        
                    JOBS[job_id]["completed"] += 1
                    
                except Exception as e:
                    JOBS[job_id]["errors"].append(f"Lỗi khi dịch chương {cid}: {e}")
                    JOBS[job_id]["completed"] += 1
                    
                # Tôn trọng rate limit
                time.sleep(cfg.get("sleep_time", 2))
                
            if JOBS[job_id]["status"] != "cancelled":
                JOBS[job_id]["status"] = "completed"
                
            # Cập nhật glossary chung vào disk khi xong job
            if hasattr(translator, 'glossary_manager'):
                translator.glossary_manager.save_dictionary()
                
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["errors"].append(f"Lỗi hệ thống: {str(e)}")


# --- API ENDPOINTS ---

@app.post("/translate")
def start_translation(req: TranslateRequest, background_tasks: BackgroundTasks):
    """
    1. API Dịch (Background): Nhận start_chapter và end_chapter.
    Kiểm tra những chương nào đã được dịch và skip chúng.
    Khởi tạo Job và trả về Job ID.
    """
    if req.config_name not in CONFIG_MAP:
        raise HTTPException(status_code=400, detail=f"config_name phải thuộc {list(CONFIG_MAP.keys())}")
        
    cfg = CONFIG_MAP[req.config_name]
    output_dir = cfg.get("output_dir", "./translated_chapters")
    os.makedirs(output_dir, exist_ok=True)
    
    # Phân loại chương nào cần dịch, chương nào đã có
    already_translated = []
    to_translate =[]
    
    for cid in range(req.start_chapter, req.end_chapter + 1):
        # Trùng khớp với format lưu của TranslatorCore
        filepath = os.path.join(output_dir, f"Chapter_{cid}.txt")
        if os.path.exists(filepath):
            already_translated.append(cid)
        else:
            to_translate.append(cid)
            
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "total": len(to_translate),
        "completed": 0,
        "current_chapter": None,
        "errors":[]
    }
    
    if to_translate:
        background_tasks.add_task(translation_worker, job_id, req.start_chapter, req.end_chapter, to_translate, cfg)
        status_msg = f"Job dịch đã được bắt đầu ở dưới nền ({'Batch' if cfg.get('use_batch_mode') else 'Sequential'})."
    else:
        JOBS[job_id]["status"] = "completed"
        status_msg = "Tất cả các chương yêu cầu đều đã được dịch từ trước."

    return {
        "message": status_msg,
        "job_id": job_id,
        "already_translated": already_translated,
        "to_translate": to_translate
    }


@app.get("/track-progress/{job_id}")
def track_progress(job_id: str):
    """2. API Track Progress: Xem tiến độ của job dịch."""
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Không tìm thấy Job ID này.")
    return JOBS[job_id]


@app.get("/chapter/{chapter_id}")
def get_chapter(chapter_id: int, config_name: str = "sequential_config"):
    """3. API Lấy chương: Trả về nội dung txt của chương đã được dịch."""
    if config_name not in CONFIG_MAP:
        raise HTTPException(status_code=400, detail="config_name không hợp lệ.")
        
    cfg = CONFIG_MAP[config_name]
    output_dir = cfg.get("output_dir", "./translated_chapters")
    
    # Trùng khớp với format lưu của TranslatorCore
    filepath = os.path.join(output_dir, f"Chapter_{chapter_id}.txt")
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail=f"Chương {chapter_id} chưa được dịch (Không tìm thấy file).")
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    return {
        "chapter_id": chapter_id,
        "content": content
    }


@app.get("/get-book")
def get_book(config_name: str = "sequential_config", book_title: str = "Quỷ Bí Chi Chủ"):
    """
    4. API Get Book: Gom toàn bộ các file TXT đã dịch lại, tạo EPUB và trả về dưới dạng file download.
    """
    if config_name not in CONFIG_MAP:
        raise HTTPException(status_code=400, detail="config_name không hợp lệ.")
        
    cfg = CONFIG_MAP[config_name]
    output_dir = cfg.get("output_dir", "./translated_chapters")
    
    if not os.path.exists(output_dir):
        raise HTTPException(status_code=404, detail="Thư mục chứa chương dịch chưa được tạo.")
        
    # Lấy toàn bộ file txt và sắp xếp
    txt_files =[
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if f.endswith(".txt")
    ]
    txt_files.sort(key=lambda x: extract_number(os.path.basename(x)))
    
    if not txt_files:
        raise HTTPException(status_code=404, detail="Chưa có chương nào được dịch để tạo sách.")
        
    # Tạo tên file output ngẫu nhiên tránh đụng độ nếu nhiều request gọi cùng lúc
    epub_filename = f"Book_{uuid.uuid4().hex[:8]}.epub"
    epub_filepath = os.path.join(output_dir, epub_filename)
    
    try:
        # Gọi hàm tạo EPUB từ make_book.py
        create_epub_from_txt(
            txt_files=txt_files,
            output_file=epub_filepath,
            book_title=book_title,
            author="Mực Thích Lặn Nước"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi tạo Epub: {e}")
        
    return FileResponse(
        path=epub_filepath, 
        media_type='application/epub+zip', 
        filename=f"{book_title}.epub"
    )
@app.get("/jobs")
def list_jobs():
    """5. API List Jobs: Lấy danh sách toàn bộ các job đang chạy, đã xong hoặc bị lỗi."""
    # Chuyển đổi từ dạng Dictionary sang dạng List để dễ hiển thị
    job_list = list(JOBS.values())
    
    # Bạn có thể sắp xếp job mới nhất lên đầu nếu muốn (nếu có lưu thời gian)
    # Ở đây mình trả về thẳng số lượng và danh sách
    return {
        "total_jobs": len(job_list),
        "jobs": job_list
    }
if __name__ == "__main__":
    # Khởi chạy server tại http://localhost:8000
    uvicorn.run("server:app", host="0.0.0.0", port=80, reload=True)