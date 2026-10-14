import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from app.llm.groq import MAX_ATTEMPTS, GroqClient, ReasonerUnavailable
from app.llm.structured import required_schema


class Answer(BaseModel):
    label: str
    confidence: float


DRAFT: dict[str, Any] = {"label": "false", "confidence": 0.9}


class FakeGroq:
    def __init__(self, *replies: httpx.Response | Exception) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def ok(content: dict[str, Any] = DRAFT) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})


def limited(retry_after: str) -> httpx.Response:
    return httpx.Response(429, headers={"retry-after": retry_after}, json={"error": {}})


def run(fake: FakeGroq) -> tuple[Answer, list[float]]:
    waits: list[float] = []
    http = httpx.Client(base_url="https://groq.test", transport=httpx.MockTransport(fake))
    client = GroqClient("key", http=http, sleep=waits.append)
    return client.structured("openai/gpt-oss-120b", Answer, "sys", "prompt"), waits


def test_request_uses_strict_schema_and_deterministic_settings() -> None:
    fake = FakeGroq(ok())
    run(fake)
    [body] = fake.bodies
    assert body["temperature"] == 0
    assert body["reasoning_effort"] == "medium"
    response_format = body["response_format"]["json_schema"]
    assert response_format["strict"] is True
    assert response_format["schema"] == required_schema(Answer)


def test_rate_limit_waits_for_retry_after_then_succeeds() -> None:
    draft, waits = run(FakeGroq(limited("6.63"), ok()))
    assert draft.label == "false"
    assert waits == [6.63]


def test_long_rate_limit_gives_up_at_once_for_the_fallback() -> None:
    fake = FakeGroq(limited("90"))
    with pytest.raises(ReasonerUnavailable, match="429"):
        run(fake)
    assert len(fake.bodies) == 1


def test_server_errors_retry_with_backoff_then_give_up() -> None:
    fake = FakeGroq(*[httpx.Response(503) for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(ReasonerUnavailable, match="503"):
        run(fake)
    assert len(fake.bodies) == MAX_ATTEMPTS


def test_network_failure_is_unavailable_not_a_crash() -> None:
    fake = FakeGroq(*[httpx.ConnectError("down") for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(ReasonerUnavailable, match="network"):
        run(fake)


def test_client_errors_fall_back_at_once_with_groq_reason() -> None:
    error = {"error": {"code": "model_not_found", "message": "The model does not exist"}}
    fake = FakeGroq(httpx.Response(400, json=error))
    with pytest.raises(ReasonerUnavailable, match=r"400.*model_not_found"):
        run(fake)
    assert len(fake.bodies) == 1


def test_repeated_failed_generations_fall_back_with_groq_reason() -> None:
    error = {"error": {"code": "json_validate_failed", "message": "Failed to generate JSON"}}
    fake = FakeGroq(*[httpx.Response(400, json=error) for _ in range(MAX_ATTEMPTS)])
    with pytest.raises(ReasonerUnavailable, match=r"400.*json_validate_failed"):
        run(fake)
    assert len(fake.bodies) == MAX_ATTEMPTS


def test_a_failed_generation_is_sampled_again() -> None:
    error = {"error": {"code": "output_parse_failed", "message": "Parsing failed"}}
    fake = FakeGroq(httpx.Response(400, json=error), ok())
    draft, waits = run(fake)
    assert draft.label == "false"
    assert len(fake.bodies) == 2
    assert waits == []


def test_reasoning_effort_is_set_per_client() -> None:
    fake = FakeGroq(ok())
    http = httpx.Client(base_url="https://groq.test", transport=httpx.MockTransport(fake))
    GroqClient("key", http=http, reasoning_effort="low").structured("m", Answer, "s", "p")
    assert fake.bodies[0]["reasoning_effort"] == "low"
