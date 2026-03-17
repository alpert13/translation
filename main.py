from config import batch_config, sequential_config, deepseek_config, coi_config, coi_deepseek_config
from translator import TranslatorCore

def get_provider(config: dict):
    provider_name = config.get("provider", "gemini").lower()
    
    if provider_name == "gemini":
        from llms.gemini import GeminiProvider
        return GeminiProvider(config)
    elif provider_name == "deepseek":
        from llms.deepseek import DeepSeekProvider
        return DeepSeekProvider(config)
    else:
        raise ValueError(f"Không hỗ trợ provider: {provider_name}")

if __name__ == "__main__":
    # CHỌN CẤU HÌNH BẠN MUỐN DÙNG
    # Các tùy chọn: batch_config, sequential_config, deepseek_config, coi_config, coi_deepseek_config
    selected_config = coi_deepseek_config
    
    print(f"Đang khởi tạo ứng dụng dịch giả với cấu hình: {selected_config.get('provider').upper()}")
    
    # Khởi tạo provider và core
    provider = get_provider(selected_config)
    translator = TranslatorCore(selected_config, provider)
    
    # Chạy
    translator.run()