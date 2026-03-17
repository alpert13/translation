import os
import re
import time
from typing import Iterator
from tqdm import tqdm
import data
from glossary import GlossaryManager
from llms.base import BaseLLMProvider
from prompts import build_prompt
from pathway_detector import get_pathway_json_block

class TranslatorCore:
    def __init__(self, config: dict, llm_provider: BaseLLMProvider):
        self.config = config
        self.llm = llm_provider
        
        self.start_chapter = config.get("start_chapter", 1)
        self.end_chapter = config.get("end_chapter", 10)
        self.pickle_file = config.get("pickle_file", "./text.pkl")
        self.output_dir = config.get("output_dir", "./translated_chapters")
        self.batch_requests_dir = config.get("batch_requests_dir", "./batch_requests")
        self.sleep_time = config.get("sleep_time", 5)
        
        self.use_batch_mode = config.get("use_batch_mode", False)
        self.batch_size = config.get("batch_size", 50)
        self.batch_poll_interval = config.get("batch_poll_interval", 60)
        
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.batch_requests_dir, exist_ok=True)
        
        self.glossary_manager = GlossaryManager(config.get("glossary_file", "./lotm_glossary.json"))

    def _extract_and_learn_terms(self, translation: str) -> str:
        clean_translation = translation
        new_terms = {}
        
        match = re.search(r'\[(.*?)\]\s*$', translation)
        if match:
            content_inside_brackets = match.group(1).strip()
            if content_inside_brackets:
                pairs = content_inside_brackets.split('|')
                for pair in pairs:
                    if ':' in pair:
                        eng, vie = pair.split(':', 1)
                        new_terms[eng.strip()] = vie.strip()
            clean_translation = translation[:match.start()].strip()
            
        if new_terms:
            print(f"  -> [Học từ mới]: {new_terms}")
            self.glossary_manager.update_dictionary(new_terms)
            
        return clean_translation

    def build_chapter_prompt(self, chapter: dict) -> str:
        c_title = chapter["title"]
        c_text = chapter["text"]
        relevant_glossary = self.glossary_manager.get_relevant_glossary(c_text)
        pathway_block = get_pathway_json_block(c_text, self.config.get("pathway_file", "pathway.json"))
        return build_prompt(c_title, c_text, relevant_glossary, pathway_block)

    def translate_chapter_stream(self, chapter: dict) -> Iterator[str]:
        prompt = self.build_chapter_prompt(chapter)
        for chunk in self.llm.translate_chapter_stream(prompt):
            yield chunk

    def translate_chapter_once(self, chapter: dict) -> str:
        prompt = self.build_chapter_prompt(chapter)
        return self.llm.translate_chapter(prompt)

    def process_and_save_translation(self, chapter_id: int, translation_raw: str) -> str:
        translated_content = self._extract_and_learn_terms(translation_raw)
        output_path = os.path.join(self.output_dir, f"Chapter_{chapter_id}.txt")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(translated_content)
        return output_path

    def run_sequential_loop(self):
        print(f"=== BẮT ĐẦU HỆ THỐNG DỊCH (SEQUENTIAL MODE) ===")
        print(f"- Provider: {self.config.get('provider', 'unknown')}")
        print(f"- Model: {self.config.get('model_name')}")
        print(f"- Nhiệt độ: {self.config.get('temperature')}")
        print(f"- Dịch từ chương {self.start_chapter} đến chương {self.end_chapter}")
        print(f"- Từ điển hiện tại có: {len(self.glossary_manager.get_dict())} từ")
        print("================================================\n")

        try:
            all_chapters = data.load_chapters(self.pickle_file)
        except Exception as e:
            print(f"Không thể tải file {self.pickle_file}. Lỗi: {e}")
            return

        for chapter in tqdm(all_chapters):
            c_id = chapter['chapter_id']
            c_title = chapter['title']
            c_text = chapter['text']
            
            if self.start_chapter <= c_id <= self.end_chapter:
                output_path = os.path.join(self.output_dir, f"Chapter_{c_id}.txt")
                
                if os.path.exists(output_path):
                    print(f"[*] Chương {c_id} ({c_title}) đã được dịch. Bỏ qua.")
                    continue
                
                print(f"\n[*] Đang dịch Chương {c_id}: {c_title} (Độ dài: {len(c_text)} ký tự)")
                print("  -> Đang quét dò tìm Pathway (Levenshtein)...")
                
                print(f"  -> Bắt đầu gọi API ({self.config.get('model_name')})...")
                translation_raw = self.translate_chapter_once(chapter)
                self.process_and_save_translation(c_id, translation_raw)
                
                print(f"  -> Đã lưu bản dịch tại: {output_path}")
                time.sleep(self.sleep_time)

    def run_batch_loop(self):
        print(f"=== BẮT ĐẦU HỆ THỐNG DỊCH (BATCH MODE) ===")
        print(f"- Provider: {self.config.get('provider', 'unknown')}")
        print(f"- Model: {self.config.get('model_name')}")
        print(f"- Nhiệt độ: {self.config.get('temperature')}")
        print(f"- Dịch từ chương {self.start_chapter} đến chương {self.end_chapter}")
        print(f"- Batch size: {self.batch_size} chương/batch")
        print(f"- Từ điển hiện tại có: {len(self.glossary_manager.get_dict())} từ")
        print("==========================================\n")

        if not self.llm.supports_batch():
            print(f"[!] Provider {self.config.get('provider')} không hỗ trợ chế độ Batch API.")
            print("Chuyển sang chế độ Sequential an toàn...")
            self.run_sequential_loop()
            return

        try:
            all_chapters = data.load_chapters(self.pickle_file)
        except Exception as e:
            print(f"Không thể tải file {self.pickle_file}. Lỗi: {e}")
            return

        chapters_to_translate = []
        for chapter in all_chapters:
            c_id = chapter['chapter_id']
            if self.start_chapter <= c_id <= self.end_chapter:
                output_path = os.path.join(self.output_dir, f"Chapter_{c_id}.txt")
                if not os.path.exists(output_path):
                    chapters_to_translate.append(chapter)
                else:
                    print(f"[*] Chương {c_id} đã được dịch. Bỏ qua.")
        
        if not chapters_to_translate:
            print("Không có chương nào cần dịch!")
            return
        
        print(f"Tổng số chương cần dịch: {len(chapters_to_translate)}\n")
        
        batches = []
        for i in range(0, len(chapters_to_translate), self.batch_size):
            batches.append(chapters_to_translate[i:i + self.batch_size])
        
        print(f"Chia thành {len(batches)} batch(es)\n")
        
        # Gọi xuống LLM để xử lý batch job
        results = self.llm.run_batch(
            batches=batches, 
            output_dir=self.output_dir, 
            glossary_manager=self.glossary_manager,
            batch_requests_dir=self.batch_requests_dir,
            batch_poll_interval=self.batch_poll_interval
        ) or {}
        
        # Lưu kết quả và học từ
        for chapter_id, translation in results.items():
            output_path = self.process_and_save_translation(chapter_id, translation)
            print(f"  -> Đã lưu Chapter {chapter_id}: {output_path}")

        if any(results.values()):
            self.glossary_manager.save_dictionary()

        print(f"\n{'='*60}")
        print("HOÀN THÀNH TẤT CẢ BATCH!")
        print(f"{'='*60}")

    def run(self):
        if self.use_batch_mode:
            self.run_batch_loop()
        else:
            self.run_sequential_loop()
