import os
import time
import uuid
import json
from typing import List, Optional, Dict
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

# Import từ các file local của bạn
from config import sequential_config, deepseek_config, coi_config, batch_config
from data import load_chapters
from glossary import GlossaryManager
from pathway_detector import get_pathway_json_block
from gemini import GeminiProvider
from deepseek import DeepSeekProvider
from make_book import create_epub_from_txt, extract_number

# Fallback nếu thiếu file prompts.py
try:
    from prompts import build_prompt
except ImportError:
    def build_prompt(title, text, glossary, pathway):
        return (f"Bạn là dịch giả chuyên nghiệp cho tiểu thuyết 'Lord of the Mysteries'.\n"
                f"Tên chương: {title}\n"
                f"Thuật ngữ (Glossary): {json.dumps(glossary, ensure_ascii=False)}\n"
                f"Con đường (Pathway): \n{pathway}\n\n"
                f"Dịch nội dung sau sang tiếng Việt:\n\n{text}")

app = FastAPI(title="LOTM Translation API", description="API server for novel translation system")

# In-memory database để lưu trạng thái của các job dịch
JOBS: Dict[str, dict] = {}

# Dictionary để map tên config với biến config thực tế từ config.py
CONFIG_MAP = {
    "sequential_config": sequential_config,
    "deepseek_config": deepseek_config,
    "coi_config": coi_config,
    "batch_config": batch_config
}

# --- MODELS ---
class TranslateRequest(BaseModel):
    start_chapter: int
    end_chapter: int
    config_name: str = "sequential_config"

# --- WORKER FUNCTIONS ---
def translation_worker(job_id: str, to_translate: List[int], cfg: dict):
    """Hàm chạy nền (background task) để dịch tuần tự các chương."""
    
    JOBS[job_id]["status"] = "running"
    output_dir = cfg.get("output_dir", "./translated_chapters")
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Khởi tạo Provider & Tool
    if cfg.get("provider") == "gemini":
        provider = GeminiProvider(cfg)
    else:
        provider = DeepSeekProvider(cfg)
        
    glossary_manager = GlossaryManager(cfg.get("glossary_file", "./lotm_glossary.json"))
    
    # 2. Tải toàn bộ text từ file pickle
    pickle_file = cfg.get("pickle_file", "./text.pkl")
    try:
        chapters = load_chapters(pickle_file)
        chapter_dict = {ch['chapter_id']: ch for ch in chapters}
    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["errors"].append(f"Không thể load file {pickle_file}: {e}")
        return

    # 3. Tiến hành dịch từng chương
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
            # Thu thập context
            rel_glossary = glossary_manager.get_relevant_glossary(ch['text'])
            pw_block = get_pathway_json_block(ch['text'])
            prompt = build_prompt(ch['title'], ch['text'], rel_glossary, pw_block)
            
            # Dịch
            translated_text = provider.translate_chapter(prompt)
            
            # Lưu file txt
            filename = f"chap_{cid:04d}.txt"
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Chương {cid}: {ch['title']}\n\n")
                f.write(translated_text)
                
            JOBS[job_id]["completed"] += 1
            
        except Exception as e:
            JOBS[job_id]["errors"].append(f"Lỗi khi dịch chương {cid}: {e}")
            JOBS[job_id]["completed"] += 1
            
        # Tôn trọng rate limit
        time.sleep(cfg.get("sleep_time", 2))
        
    if JOBS[job_id]["status"] != "cancelled":
        JOBS[job_id]["status"] = "completed"


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
        filepath = os.path.join(output_dir, f"chap_{cid:04d}.txt")
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
        background_tasks.add_task(translation_worker, job_id, to_translate, cfg)
        status_msg = "Job dịch đã được bắt đầu ở dưới nền."
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
    filepath = os.path.join(output_dir, f"chap_{chapter_id:04d}.txt")
    
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

if __name__ == "__main__":
    # Khởi chạy server tại http://localhost:8000
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)