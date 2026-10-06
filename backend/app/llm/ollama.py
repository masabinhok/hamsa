"""Thin Ollama client for schema-constrained JSON (ADR 0006).

Ollama decodes against the JSON schema given in `format`, so responses are always
syntactically valid JSON of the right shape. Pydantic still validates them, because
the schema cannot express every rule (word limits, cross-field checks).
"""

import base64
import io
from collections.abc import Sequence
from typing import Any

import httpx
from PIL import Image
from pydantic import BaseModel

from app.llm.structured import Check, Messages, call_with_retry, required_schema

KEEP_ALIVE = "30m"  # keeps the vision model resident between cases (ADR 0007)
NUM_CTX = 8192  # 16k spills 39% of the 8B model to the CPU (architecture section 7)
TIMEOUT_S = 300.0
JPEG_QUALITY = 90


def encode_image(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class OllamaClient:
    def __init__(self, base_url: str, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(base_url=base_url, timeout=TIMEOUT_S)

    def structured[T: BaseModel](
        self,
        model: str,
        output: type[T],
        system: str,
        prompt: str,
        images: Sequence[Image.Image] = (),
        schema: dict[str, Any] | None = None,
        check: Check | None = None,
    ) -> T:
        messages: Messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt, "images": [encode_image(i) for i in images]},
        ]
        format_schema = schema or required_schema(output)
        return call_with_retry(
            lambda m: self._chat(model, m, format_schema), messages, output, check
        )

    def embed(self, model: str, texts: Sequence[str], *, batch: bool = False) -> list[list[float]]:
        """Embeddings. Per-case queries run on the CPU, leaving the GPU to the vision model;
        offline corpus indexing (`batch=True`) uses the GPU and unloads right after (ADR 0007).
        """
        response = self._http.post(
            "/api/embed",
            json={
                "model": model,
                "input": list(texts),
                "keep_alive": "0" if batch else KEEP_ALIVE,
                "options": {} if batch else {"num_gpu": 0},
            },
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body["embeddings"]

    def _chat(self, model: str, messages: list[dict[str, Any]], schema: dict[str, Any]) -> str:
        response = self._http.post(
            "/api/chat",
            json={
                "model": model,
                "messages": messages,
                "format": schema,
                "stream": False,
                "keep_alive": KEEP_ALIVE,
                "options": {"temperature": 0, "num_ctx": NUM_CTX},
            },
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        return body["message"]["content"]
