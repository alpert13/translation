import os
from google.genai.types import ThinkingLevel

# CẤU HÌNH CHO BATCH MODE (Đề xuất cho khối lượng lớn)
batch_config = {
    "provider": "gemini",
    "model_name": "gemini-3-flash-preview",
    "temperature": 0.25,
    "start_chapter": 1,
    "end_chapter": 5,
    "pickle_file": "./text.pkl",
    "glossary_file": "./lotm_glossary.json",
    "output_dir": "./translated_chapters",
    "batch_requests_dir": "./batch_requests",
    
    # BATCH MODE SETTINGS
    "use_batch_mode": True,
    "batch_size": 50,
    "batch_poll_interval": 60,
}

# CẤU HÌNH CHO SEQUENTIAL MODE (Gemini)
sequential_config = {
    "provider": "gemini",
    "model_name": "gemini-3-flash-preview",
    "temperature": 0.25,
    "thinking_level": ThinkingLevel.LOW,
    "start_chapter": 1,
    "end_chapter": 1445,
    "pickle_file": "./text.pkl",
    "glossary_file": "./lotm_glossary.json",
    "output_dir": "./translated_chapters",
    "sleep_time": 4,
    
    # SEQUENTIAL MODE
    "use_batch_mode": False,
}

# CẤU HÌNH CHO DEEPSEEK (Chỉ hỗ trợ tuần tự)
deepseek_config = {
    "provider": "deepseek",
    "model_name": "deepseek-chat", # Hoặc "deepseek-reasoner"
    "temperature": 0.3,
    "start_chapter": 1,
    "end_chapter": 1445,
    "pickle_file": "./text.pkl",
    "glossary_file": "./lotm_glossary.json",
    "output_dir": "./translated_chapters",
    "sleep_time": 2, # DeepSeek có thể giới hạn rate limit khác
    
    # DEEPSEEK KHÔNG HỖ TRỢ BATCH MODE HIỆN TẠI
    "use_batch_mode": False,
}

# CẤU HÌNH CHO CIRCLE OF INEVITABILITY (Sử dụng Gemini Batch Mode vì số lượng chapter lớn)
coi_config = {
    "provider": "gemini",
    "model_name": "gemini-3-flash-preview",
    "temperature": 0.25,
    "start_chapter": 1,
    "end_chapter": 1180,
    "pickle_file": "./coi_text.pkl",
    "glossary_file": "./lotm_glossary.json", # Could make a specific one if needed
    "output_dir": "./coi_translated_chapters",
    "batch_requests_dir": "./coi_batch_requests",
    
    # BATCH MODE SETTINGS
    "use_batch_mode": True,
    "batch_size": 50,
    "batch_poll_interval": 60,
}

# CẤU HÌNH CHO CIRCLE OF INEVITABILITY TEST VỚI DEEPSEEK (3 chương đầu)
coi_deepseek_config = {
    "provider": "deepseek",
    "model_name": "deepseek-reasoner", # Hoặc "deepseek-reasoner"
    "temperature": 1.3,
    "start_chapter": 163,
    "end_chapter": 200,
    "pickle_file": "./coi_text.pkl",
    "glossary_file": "./coi_glossary.json",
    "output_dir": "./coi_translated_chapters",
    "sleep_time": 2,
    
    # DEEPSEEK KHÔNG HỖ TRỢ BATCH MODE HIỆN TẠI
    "use_batch_mode": False,
}
