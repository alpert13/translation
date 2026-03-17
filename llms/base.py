from abc import ABC, abstractmethod
from typing import Iterator

class BaseLLMProvider(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model_name")
        self.temperature = config.get("temperature", 0.3)

    @abstractmethod
    def translate_chapter(self, prompt: str) -> str:
        """Dịch 1 chương (tuần tự) và trả về text raw"""
        pass

    def translate_chapter_stream(self, prompt: str) -> Iterator[str]:
        """Dịch 1 chương ở chế độ stream; mặc định fallback sang non-stream."""
        yield self.translate_chapter(prompt)

    def supports_batch(self) -> bool:
        """Trả về True nếu provider hỗ trợ Batch API"""
        return False
        
    def run_batch(self, batches: list, output_dir: str, glossary_manager, 
                  batch_requests_dir: str, batch_poll_interval: int) -> None:
        """Chạy batch mode (nếu hỗ trợ)"""
        raise NotImplementedError("Provider này không hỗ trợ batch mode")
