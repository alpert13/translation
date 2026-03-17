import os
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Import các thành phần từ hệ thống hiện tại
from config import (
    batch_config, 
    sequential_config, 
    deepseek_config, 
    coi_config, 
    coi_deepseek_config
)
from main import get_provider
from translator import TranslatorCore
import data

app = FastAPI(
    title="LOTM Translator API",
    description="API Server cho hệ thống dịch thuật Lord of the Mysteries / Circle of Inevitability",
    version="1.0.0"
)

# === CÁC MODEL DỮ LIỆU ===
class TranslateTextRequest(BaseModel):
    title: str = "Unknown Title"
    text: str
    provider: str = "gemini"  # "gemini" hoặc "deepseek"

class SystemRunRequest(BaseModel):
    config_name: str = "sequential"  # "batch", "sequential", "deepseek", "coi", "coi_deepseek"

# === HÀM HỖ TRỢ ===
def run_system_background(config_name: str):
    configs = {
        "batch": batch_config,
        "sequential": sequential_config,
        "deepseek": deepseek_config,
        "coi": coi_config,
        "coi_deepseek": coi_deepseek_config
    }
    cfg = configs.get(config_name, sequential_config)
    provider = get_provider(cfg)
    translator = TranslatorCore(cfg, provider)
    translator.run()

# === API ENDPOINTS ===
@app.get("/")
def read_root():
    return {"status": "ok", "message": "LOTM Translator API Server is running."}

@app.post("/api/translate/text")
def translate_custom_text(req: TranslateTextRequest):
    """Dịch một đoạn text/chương tùy chỉnh tự nhập vào."""
    cfg = sequential_config.copy() if req.provider == "gemini" else deepseek_config.copy()
    
    try:
        provider = get_provider(cfg)
        translator = TranslatorCore(cfg, provider)
        
        # Tạo một chapter giả lập để đẩy vào prompt
        chapter_mock = {
            "chapter_id": 99999,
            "title": req.title,
            "text": req.text
        }
        
        raw_translation = translator.translate_chapter_once(chapter_mock)
        clean_translation = translator._extract_and_learn_terms(raw_translation)
        
        return {
            "original_title": req.title,
            "translated_text": clean_translation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/translate/chapter/{chapter_id}")
def translate_chapter_by_id(chapter_id: int, provider: str = "gemini"):
    """Lấy chương từ file Pickle (text.pkl) và dịch on-the-fly."""
    cfg = sequential_config.copy() if provider == "gemini" else deepseek_config.copy()
    pickle_file = cfg.get("pickle_file", "./text.pkl")
    
    if not os.path.exists(pickle_file):
         raise HTTPException(status_code=404, detail=f"Không tìm thấy file {pickle_file}")

    try:
        chapter = data.get_chapter_by_id(chapter_id, pickle_file)
        if not chapter:
            raise HTTPException(status_code=404, detail="Không tìm thấy chương này trong database (pickle).")
            
        llm_provider = get_provider(cfg)
        translator = TranslatorCore(cfg, llm_provider)
        
        raw_translation = translator.translate_chapter_once(chapter)
        clean_translation = translator._extract_and_learn_terms(raw_translation)
        
        return {
            "chapter_id": chapter_id,
            "title": chapter["title"],
            "translated_text": clean_translation
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chapters/{chapter_id}")
def get_translated_chapter(chapter_id: int):
    """Đọc file kết quả của một chương ĐÃ dịch xong."""
    output_dir = sequential_config.get("output_dir", "./translated_chapters")
    file_path = os.path.join(output_dir, f"Chapter_{chapter_id}.txt")
    
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"chapter_id": chapter_id, "content": content}
    else:
        raise HTTPException(status_code=404, detail="Chưa có bản dịch cho chương này.")

@app.post("/api/system/start")
def start_translation_system(req: SystemRunRequest, background_tasks: BackgroundTasks):
    """Kích hoạt hệ thống dịch (Sequential/Batch) chạy ngầm."""
    valid_configs = ["batch", "sequential", "deepseek", "coi", "coi_deepseek"]
    if req.config_name not in valid_configs:
        raise HTTPException(status_code=400, detail=f"Cấu hình phải là một trong: {valid_configs}")
        
    background_tasks.add_task(run_system_background, req.config_name)
    return {"message": f"Hệ thống dịch thuật đã được khởi chạy ngầm với cấu hình: {req.config_name}"}

if __name__ == "__main__":
    # Khởi chạy server khi chạy trực tiếp file này
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)