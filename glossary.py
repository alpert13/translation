import os
import json
from thefuzz import fuzz

class GlossaryManager:
    def __init__(self, glossary_file: str = "./lotm_glossary.json"):
        self.glossary_file = glossary_file
        self.master_dictionary = self._load_dictionary()

    def _load_dictionary(self) -> dict:
        default_dict = {
            "Beyonder": "Người Phi Phàm", "Sequence": "Danh sách",
            "Pathway": "Con đường", "Potion": "Ma dược",
            "The Fool": "Kẻ Khờ", "Tarot Club": "Hội Bài Tarot",
            "Nighthawks": "Kẻ Gác Đêm", "Klein Moretti": "Klein Moretti"
        }
        if os.path.exists(self.glossary_file):
            try:
                with open(self.glossary_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Lỗi đọc file {self.glossary_file}: {e}")
        return default_dict

    def save_dictionary(self):
        try:
            with open(self.glossary_file, 'w', encoding='utf-8') as f:
                json.dump(self.master_dictionary, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"[!] Lỗi lưu từ điển: {e}")

    def update_dictionary(self, new_terms: dict):
        self.master_dictionary.update(new_terms)
        self.save_dictionary()

    def get_dict(self) -> dict:
        return self.master_dictionary

    def get_relevant_glossary(self, text: str, threshold: int = 85) -> dict:
        relevant_terms = {}
        text_lower = text.lower()
        for eng_term, vie_translation in self.master_dictionary.items():
            if eng_term.lower() in text_lower:
                relevant_terms[eng_term] = vie_translation
            elif fuzz.partial_ratio(eng_term.lower(), text_lower) >= threshold:
                relevant_terms[eng_term] = vie_translation
        return relevant_terms
