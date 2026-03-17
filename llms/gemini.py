import os
import json
import time
from typing import Iterator
from dotenv import load_dotenv
from google import genai
from google.genai import types

from .base import BaseLLMProvider
from prompts import build_prompt

class GeminiProvider(BaseLLMProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        load_dotenv()
        self.client = genai.Client()
        self.thinking_level = config.get("thinking_level", types.ThinkingLevel.LOW)

    def translate_chapter(self, prompt: str) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature,
                        thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level)
                    )
                )
                return response.text
                
            except Exception as e:
                print(f"  -> [!] Lỗi API Gemini (Lần {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    return f"[!] LỖI DỊCH CHƯƠNG NÀY: {e}"

    def translate_chapter_stream(self, prompt: str) -> Iterator[str]:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature,
                        thinking_config=types.ThinkingConfig(thinking_level=self.thinking_level)
                    )
                )

                for chunk in response:
                    chunk_text = getattr(chunk, "text", None)
                    if chunk_text:
                        yield chunk_text
                return
            except Exception as e:
                print(f"  -> [!] Lỗi stream Gemini (Lần {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    yield f"[!] LỖI DỊCH CHƯƠNG NÀY: {e}"
                    return

    def supports_batch(self) -> bool:
        return True

    def _create_batch_jsonl(self, chapters_batch: list, batch_num: int, 
                            batch_requests_dir: str, glossary_manager) -> str:
        jsonl_filename = os.path.join(
            batch_requests_dir, 
            f"batch_{batch_num}_chapters_{chapters_batch[0]['chapter_id']}_to_{chapters_batch[-1]['chapter_id']}.jsonl"
        )
        
        from pathway_detector import get_pathway_json_block

        with open(jsonl_filename, 'w', encoding='utf-8') as f:
            for chapter in chapters_batch:
                c_id = chapter['chapter_id']
                c_title = chapter['title']
                c_text = chapter['text']
                
                relevant_glossary = glossary_manager.get_relevant_glossary(c_text)
                pathway_block = get_pathway_json_block(c_text, self.config.get("pathway_file", "pathway.json"))
                prompt = build_prompt(c_title, c_text, relevant_glossary, pathway_block)
                
                request_obj = {
                    "key": f"chapter-{c_id}",
                    "request": {
                        "contents": [{
                            "parts": [{"text": prompt}],
                            "role": "user"
                        }],
                        "generation_config": {
                            "temperature": self.temperature
                        }
                    }
                }
                f.write(json.dumps(request_obj, ensure_ascii=False) + "\n")
        
        print(f"  -> Đã tạo file batch request: {jsonl_filename}")
        return jsonl_filename

    def _submit_batch_job(self, jsonl_file: str, batch_num: int) -> str:
        print(f"  -> Đang upload file batch {batch_num}...")
        try:
            uploaded_file = self.client.files.upload(
                file=jsonl_file,
                config=types.UploadFileConfig(
                    display_name=f'lotm-batch-{batch_num}',
                    mime_type='jsonl'
                )
            )
            print(f"  -> Upload thành công: {uploaded_file.name}")
            
            batch_job = self.client.batches.create(
                model=self.model_name,
                src=uploaded_file.name,
                config={'display_name': f"lotm-translation-batch-{batch_num}"}
            )
            print(f"  -> Đã tạo batch job: {batch_job.name}")
            return batch_job.name
        except Exception as e:
            print(f"  -> [!] Lỗi khi submit batch job: {e}")
            return None

    def _poll_batch_status(self, job_name: str, poll_interval: int) -> dict:
        completed_states = {'JOB_STATE_SUCCEEDED', 'JOB_STATE_FAILED', 'JOB_STATE_CANCELLED', 'JOB_STATE_EXPIRED'}
        print(f"  -> Đang theo dõi batch job: {job_name}")
        while True:
            try:
                batch_job = self.client.batches.get(name=job_name)
                current_state = batch_job.state.name
                if current_state in completed_states:
                    print(f"  -> Batch job hoàn thành với trạng thái: {current_state}")
                    return {'state': current_state, 'job': batch_job}
                print(f"  -> Trạng thái hiện tại: {current_state}. Chờ {poll_interval}s...")
                time.sleep(poll_interval)
            except Exception as e:
                print(f"  -> [!] Lỗi khi kiểm tra batch status: {e}")
                time.sleep(poll_interval)

    def _process_batch_results(self, batch_job) -> dict:
        results = {}
        try:
            if batch_job.dest and batch_job.dest.file_name:
                result_file_name = batch_job.dest.file_name
                print(f"  -> Đang tải kết quả từ file: {result_file_name}")
                file_content = self.client.files.download(file=result_file_name)
                file_text = file_content.decode('utf-8')
                
                for line in file_text.strip().split('\n'):
                    if not line:
                        continue
                    try:
                        result_obj = json.loads(line)
                        if 'key' in result_obj:
                            chapter_id = int(result_obj['key'].replace('chapter-', ''))
                            if 'response' in result_obj and result_obj['response']:
                                try:
                                    response_text = result_obj['response']['candidates'][0]['content']['parts'][0]['text']
                                    results[chapter_id] = response_text
                                except (KeyError, IndexError) as e:
                                    print(f"  -> [!] Không thể parse response cho chapter {chapter_id}: {e}")
                                    results[chapter_id] = "[!] LỖI PARSE RESPONSE"
                            elif 'error' in result_obj:
                                print(f"  -> [!] Lỗi cho chapter {chapter_id}: {result_obj['error']}")
                                results[chapter_id] = f"[!] LỖI: {result_obj['error']}"
                    except json.JSONDecodeError as e:
                        print(f"  -> [!] Không thể parse JSON line: {e}")
            elif batch_job.dest and batch_job.dest.inlined_responses:
                print(f"  -> Xử lý kết quả inline...")
                # Note: Expand if necessary based on real usages.
        except Exception as e:
            print(f"  -> [!] Lỗi khi xử lý kết quả batch: {e}")
        return results

    def run_batch(self, batches: list, output_dir: str, glossary_manager, 
                  batch_requests_dir: str, batch_poll_interval: int) -> dict:
        """
        Runs batch operations specifically for Gemini.
        Returns dictionary containing all batch results combined.
        """
        all_results = {}
        for batch_num, chapters_batch in enumerate(batches, start=1):
            print(f"\n{'='*60}")
            print(f"BATCH {batch_num}/{len(batches)}: Chương {chapters_batch[0]['chapter_id']} - {chapters_batch[-1]['chapter_id']}")
            print(f"{'='*60}")
            
            jsonl_file = self._create_batch_jsonl(chapters_batch, batch_num, batch_requests_dir, glossary_manager)
            job_name = self._submit_batch_job(jsonl_file, batch_num)
            
            if not job_name:
                print(f"[!] Không thể tạo batch job cho batch {batch_num}. Bỏ qua.")
                continue
            
            status = self._poll_batch_status(job_name, batch_poll_interval)
            
            if status['state'] == 'JOB_STATE_SUCCEEDED':
                results = self._process_batch_results(status['job'])
                all_results.update(results)
                print(f"  -> Batch {batch_num} hoàn thành thành công!")
            else:
                print(f"  -> [!] Batch {batch_num} không thành công: {status['state']}")
                if hasattr(status['job'], 'error'):
                    print(f"  -> Lỗi: {status['job'].error}")
                    
        return all_results
