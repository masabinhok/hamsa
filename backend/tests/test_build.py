from pydantic import SecretStr

from app.config import Settings
from app.llm.groq import GroqClient
from app.llm.ollama import OllamaClient
from app.pipeline.__main__ import build_pipeline


def test_without_a_groq_key_every_check_runs_on_the_local_model() -> None:
    offline = build_pipeline(Settings(groq_api_key=None, fact_check_api_key=None))
    assert [type(client) for client, _ in offline.reasoners] == [OllamaClient]
    assert offline.nepali_checker is not None
    assert isinstance(offline.nepali_checker[0], OllamaClient)
    assert offline.vet_fact_checks is not None  # corpus fact-checks are still judged
    assert offline.hosted == 0  # its drafts are fallbacks: never fast-tracked uncalibrated


def test_with_a_groq_key_the_local_model_is_the_fallback() -> None:
    hosted = build_pipeline(Settings(groq_api_key=SecretStr("gsk-test")))
    assert [type(client) for client, _ in hosted.reasoners] == [GroqClient, OllamaClient]
    assert hosted.hosted == 1
