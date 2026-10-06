import json

import httpx
from PIL import Image

from app.ingest.frames import Frame
from app.llm.ollama import OllamaClient
from app.pipeline.extract import SYSTEM, build_prompt, extract_claim
from tests.test_ollama import VALID, FakeOllama


def test_prompt_includes_post_text_and_frame_count() -> None:
    prompt = build_prompt("  रसुवामा बाढी  ", 3)
    assert prompt == "Post text:\nरसुवामा बाढी\n\n3 frame(s) from the post's media are attached."


def test_prompt_for_media_only_post() -> None:
    assert build_prompt(None, 2).startswith("Post text:\n(no text, media only)")
    assert build_prompt("   ", 0) == "Post text:\n(no text, media only)"


def test_extract_sends_the_system_prompt_and_every_frame() -> None:
    fake = FakeOllama(json.dumps(VALID))
    http = httpx.Client(base_url="http://ollama.test", transport=httpx.MockTransport(fake))
    frames = [Frame(i, float(i), Image.new("RGB", (8, 8))) for i in range(3)]

    claim = extract_claim(OllamaClient("http://ollama.test", http=http), "qwen3-vl", "x", frames)

    assert claim.claim_en == VALID["claim_en"]
    system, user = fake.requests[0]["messages"]
    assert system["content"] == SYSTEM
    assert len(user["images"]) == 3
