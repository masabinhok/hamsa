from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Optional so the pipeline can run fully local on the fallback model.
    groq_api_key: SecretStr | None = None
    reasoning_model: str = "openai/gpt-oss-120b"

    ollama_host: AnyHttpUrl = AnyHttpUrl("http://localhost:11434")
    vision_model: str = "qwen3-vl:8b-instruct"
    fallback_model: str = "qwen3:8b"

    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://localhost:6333")


@lru_cache
def get_settings() -> Settings:
    return Settings()
