import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def load() -> Settings:
    """Settings from process env only, ignoring any developer .env file."""
    return Settings(_env_file=None)  # pyright: ignore[reportCallIssue]


def test_defaults_run_fully_local() -> None:
    settings = load()
    assert settings.groq_api_key is None
    assert str(settings.ollama_host) == "http://localhost:11434/"


def test_env_overrides_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VISION_MODEL", "qwen3-vl:4b")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    settings = load()
    assert settings.vision_model == "qwen3-vl:4b"
    assert settings.qdrant_url.host == "qdrant"


def test_api_key_never_appears_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_value")
    settings = load()
    assert "gsk_secret_value" not in repr(settings)
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "gsk_secret_value"


def test_malformed_url_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_HOST", "not a url")
    with pytest.raises(ValidationError):
        load()
