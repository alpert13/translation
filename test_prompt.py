"""
Script để xem thử prompt sẽ được gửi khi dịch chương 1.
Chạy: python test_prompt.py
"""
import sys
from config import coi_deepseek_config  # Đổi config tại đây nếu cần
import data
from glossary import GlossaryManager
from prompts import build_prompt
from pathway_detector import get_pathway_json_block

TARGET_CHAPTER = 1

def main():
    config = coi_deepseek_config  # Đổi config tại đây nếu cần

    pickle_file = config.get("pickle_file", "./text.pkl")
    glossary_file = config.get("glossary_file", "./lotm_glossary.json")
    pathway_file = config.get("pathway_file", "pathway.json")

    print(f"[*] Đang tải dữ liệu từ: {pickle_file}")
    try:
        all_chapters = data.load_chapters(pickle_file)
    except Exception as e:
        print(f"[!] Không thể tải file {pickle_file}. Lỗi: {e}")
        sys.exit(1)

    chapter = next((c for c in all_chapters if c["chapter_id"] == TARGET_CHAPTER), None)
    if chapter is None:
        print(f"[!] Không tìm thấy chương {TARGET_CHAPTER}.")
        sys.exit(1)

    c_title = chapter["title"]
    c_text  = chapter["text"]

    print(f"[*] Chương {TARGET_CHAPTER}: {c_title} ({len(c_text)} ký tự)")

    glossary_manager = GlossaryManager(glossary_file)
    relevant_glossary = glossary_manager.get_relevant_glossary(c_text)
    print(f"[*] Thuật ngữ liên quan: {len(relevant_glossary)} từ")

    print("[*] Đang quét pathway...")
    pathway_block = get_pathway_json_block(c_text, pathway_file)

    prompt = build_prompt(c_title, c_text, relevant_glossary, pathway_block)

    separator = "=" * 70
    print(f"\n{separator}")
    print("PROMPT SẼ ĐƯỢC GỬI ĐẾN LLM:")
    print(separator)
    print(prompt)
    print(separator)
    print(f"Tổng độ dài prompt: {len(prompt)} ký tự")

if __name__ == "__main__":
    main()
