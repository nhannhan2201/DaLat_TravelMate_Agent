"""Đọc API key từ biến môi trường hoặc file .env ở gốc dự án."""

import os
from pathlib import Path

from dotenv import load_dotenv


_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class ConfigurationError(RuntimeError):
    """Thiếu giá trị cấu hình cần thiết cho dịch vụ."""


def _required_setting(variable_name: str) -> str:
    # Biến môi trường đã có được ưu tiên hơn giá trị trong .env.
    load_dotenv(dotenv_path=_ENV_FILE, override=False)
    value = os.getenv(variable_name, "").strip()
    if not value:
        raise ConfigurationError(
            f"Thiếu {variable_name}. Hãy đặt biến môi trường hoặc thêm vào file .env."
        )
    return value


def get_serpapi_api_key() -> str:
    """Trả về SerpApi key khi bước tìm địa điểm cần dùng."""

    return _required_setting("SERPAPI_API_KEY")


def get_deepseek_api_key() -> str:
    """Trả về key của nhà cung cấp mô hình DeepSeek."""

    return _required_setting("DEEPSEEK_API_KEY")


def get_deepseek_base_url() -> str:
    """Endpoint OpenAI-compatible của nhà cung cấp mô hình."""

    return _required_setting("DEEPSEEK_BASE_URL")


def get_deepseek_model() -> str:
    """Model ID gắn với key của nhà cung cấp."""

    return _required_setting("DEEPSEEK_MODEL")
