import os
import json
import time
from typing import Iterator
from typing import cast
from dotenv import load_dotenv
from openai import OpenAI
from .base import BaseLLMProvider

class DeepSeekProvider(BaseLLMProvider):
    def __init__(self, config: dict):
        super().__init__(config)
        load_dotenv()
        
        # Initialize OpenAI client pointed at DeepSeek
        api_key = os.environ.get('DEEPSEEK_API_KEY')
        if not api_key:
            print("[WARNING] DEEPSEEK_API_KEY not found in environment variables.")
            
        self.client = OpenAI(
            api_key=api_key, 
            base_url="https://api.deepseek.com"
        )

    def translate_chapter(self, prompt: str) -> str:
        if not self.model_name:
            return "[!] LỖI CẤU HÌNH: model_name chưa được thiết lập cho DeepSeek."

        model_name = cast(str, self.model_name)
        try:
            temperature = float(self.temperature)
        except (TypeError, ValueError):
            temperature = 0.3

        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a professional translator for the novel 'Lord of the Mysteries'."},
                        {"role": "user", "content": prompt},
                    ],
                    model=model_name,
                    temperature=temperature,
                    stream=False,
                )

                translated = response.choices[0].message.content
                return translated or ""
                
            except Exception as e:
                print(f"  -> [!] Lỗi API DeepSeek (Lần {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    return f"[!] LỖI DỊCH CHƯƠNG NÀY: {e}"

        return "[!] LỖI KHÔNG XÁC ĐỊNH TỪ DEEPSEEK"

    def translate_chapter_stream(self, prompt: str) -> Iterator[str]:
        if not self.model_name:
            yield "[!] LỖI CẤU HÌNH: model_name chưa được thiết lập cho DeepSeek."
            return

        model_name = cast(str, self.model_name)
        try:
            temperature = float(self.temperature)
        except (TypeError, ValueError):
            temperature = 0.3

        max_retries = 3
        for attempt in range(max_retries):
            try:
                stream = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a professional translator for the novel 'Lord of the Mysteries'."},
                        {"role": "user", "content": prompt},
                    ],
                    model=model_name,
                    temperature=temperature,
                    stream=True,
                )

                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if not delta:
                        continue
                    delta_text = getattr(delta, "content", None)
                    if delta_text:
                        yield delta_text
                return
            except Exception as e:
                print(f"  -> [!] Lỗi stream DeepSeek (Lần {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                else:
                    yield f"[!] LỖI DỊCH CHƯƠNG NÀY: {e}"
                    return
                    
    def supports_batch(self) -> bool:
        return False
