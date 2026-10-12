from datetime import date
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

    # Optional: without it, verdicts fall back to the local vision model (ADR 0001, 0007).
    groq_api_key: SecretStr | None = None
    reasoning_model: str = "openai/gpt-oss-120b"
    checking_model: str = "openai/gpt-oss-20b"

    ollama_host: AnyHttpUrl = AnyHttpUrl("http://localhost:11434")
    vision_model: str = "qwen3-vl:8b-instruct"
    embedding_model: str = "bge-m3"

    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://localhost:6333")
    database_url: str = f"sqlite:///{REPO_ROOT / 'data' / 'hamsa.db'}"
    media_root: Path = REPO_ROOT / "data" / "cases"

    # Shared secret for the checker desk; the desk API is disabled while unset.
    desk_token: SecretStr | None = None
    frontend_origin: str = "http://localhost:3000"

    # The disaster this deployment covers. News before this date cannot describe it;
    # fact-checks of any date still count (architecture 3.5).
    incident_start: date = date(2026, 8, 26)


@lru_cache
def get_settings() -> Settings:
    return Settings()
