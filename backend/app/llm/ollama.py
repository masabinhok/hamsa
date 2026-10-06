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
from pydantic import BaseModel, ValidationError

KEEP_ALIVE = "30m"  # keeps the vision model resident between cases (ADR 0007)
NUM_CTX = 8192  # 16k spills 39% of the 8B model to the CPU (architecture section 7)
TIMEOUT_S = 300.0
JPEG_QUALITY = 90


class StructuredOutputError(Exception):
    """The model's output failed validation twice."""


def required_schema[T: BaseModel](model: type[T]) -> dict[str, Any]:
    """The model's JSON schema with every property required.

    Constrained decoding lets a model omit optional properties, and it does: in testing,
    places, numbers, and handles were dropped from a post that had all three. Requiring
    them makes the model decide explicitly (an empty list or null) for each one.
    """
    schema = model.model_json_schema()

    def require_all(node: dict[str, Any]) -> None:
        if "properties" in node:
            node["required"] = list(node["properties"])
            for prop in node["properties"].values():
                prop.pop("default", None)
        for definition in node.get("$defs", {}).values():
            require_all(definition)

    require_all(schema)
    return schema


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
    ) -> T:
        """Chat once; on a validation error, retry once with the error shown to the model."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt, "images": [encode_image(i) for i in images]},
        ]
        schema = required_schema(output)
        content = self._chat(model, messages, schema)
        try:
            return output.model_validate_json(content)
        except ValidationError as first:
            messages += [
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": "That output is invalid:\n"
                    f"{first}\nReturn corrected JSON for the same post.",
                },
            ]
        content = self._chat(model, messages, schema)
        try:
            return output.model_validate_json(content)
        except ValidationError as second:
            raise StructuredOutputError(f"invalid after retry: {second}") from second

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
