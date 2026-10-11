import base64
import io
import json
from typing import Any

import httpx
import pytest
from PIL import Image

from app.llm.ollama import KEEP_ALIVE, NUM_CTX, OllamaClient
from app.llm.structured import StructuredOutputError, required_schema
from app.pipeline.contracts import Claim

VALID = {
    "claim": "रसुवामा हिमताल फुट्यो",
    "claim_en": "A glacial lake burst in Rasuwa",
    "places": ["रसुवा"],
    "claimed_date": None,
    "numbers": [],
    "visible_text": [],
    "watermarks": [],
    "handles": [],
    "checkable": True,
}


class FakeOllama:
    """Replies with queued message contents and records every request body."""

    def __init__(self, *replies: str | int) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        reply = self.replies.pop(0)
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": "boom"})
        return httpx.Response(200, json={"message": {"role": "assistant", "content": reply}})


def client_for(fake: FakeOllama) -> OllamaClient:
    http = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(fake))
    return OllamaClient("http://ollama.test", http=http)


def call(client: OllamaClient, images: list[Image.Image] | None = None) -> Claim:
    return client.structured("qwen3-vl", Claim, system="sys", prompt="post", images=images or [])


def test_required_schema_requires_every_property_including_nested() -> None:
    schema = required_schema(Claim)
    assert set(schema["required"]) == set(Claim.model_fields)
    assert set(schema["$defs"]["ClaimedNumber"]["required"]) == {"value", "unit", "refers_to"}
    assert all("default" not in prop for prop in schema["properties"].values())


def test_request_constrains_output_and_keeps_model_warm() -> None:
    fake = FakeOllama(json.dumps(VALID))
    call(client_for(fake), images=[Image.new("RGB", (8, 8), "red")])

    [body] = fake.requests
    assert body["model"] == "qwen3-vl"
    assert body["format"] == required_schema(Claim)
    assert body["stream"] is False
    assert body["keep_alive"] == KEEP_ALIVE
    assert body["options"] == {"temperature": 0, "num_ctx": NUM_CTX}
    system, user = body["messages"]
    assert system == {"role": "system", "content": "sys"}
    [image] = user["images"]
    assert Image.open(io.BytesIO(base64.b64decode(image))).format == "JPEG"


def test_valid_reply_is_parsed() -> None:
    claim = call(client_for(FakeOllama(json.dumps(VALID))))
    assert claim.places == ["रसुवा"]


def test_invalid_reply_is_retried_once_with_the_error_shown() -> None:
    invalid = json.dumps(VALID | {"claim": ""})
    fake = FakeOllama(invalid, json.dumps(VALID))

    claim = call(client_for(fake))

    assert claim.claim == VALID["claim"]
    retry_messages = fake.requests[1]["messages"]
    assert retry_messages[2] == {"role": "assistant", "content": invalid}
    assert "That output is invalid" in retry_messages[3]["content"]
    assert "claim" in retry_messages[3]["content"]


def test_invalid_twice_raises() -> None:
    invalid = json.dumps(VALID | {"claim": ""})
    with pytest.raises(StructuredOutputError, match="invalid after retry"):
        call(client_for(FakeOllama(invalid, invalid)))


def test_server_error_is_raised_for_the_worker_to_retry() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        call(client_for(FakeOllama(500)))


class FakeEmbed:
    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.bodies.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2] for _ in body["input"]]})


@pytest.mark.parametrize(
    ("batch", "options", "keep_alive"),
    [(False, {"num_gpu": 0}, KEEP_ALIVE), (True, {}, "0")],
    ids=["query-on-cpu", "batch-on-gpu-then-unload"],
)
def test_embed_device_and_lifetime(batch: bool, options: dict[str, int], keep_alive: str) -> None:
    fake = FakeEmbed()
    http = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(fake))

    vectors = OllamaClient("http://ollama.test", http=http).embed("bge-m3", ["a", "b"], batch=batch)

    assert vectors == [[0.1, 0.2], [0.1, 0.2]]
    [body] = fake.bodies
    assert body["options"] == options
    assert body["keep_alive"] == keep_alive
