"""Groq client: OpenAI-compatible chat completions with strict JSON schema (ADR 0001).

Free-tier limits measured 2026-10-06: 1000 requests/min but only 8000 tokens/min, so a
verdict-sized prompt can hit the token limit after one or two calls. Rate limits wait
for `retry-after` (bounded); persistent failure raises ReasonerUnavailable so the caller
falls back to the local model.
"""

import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel

from app.llm.structured import Check, Messages, call_with_retry, required_schema

BASE_URL = "https://api.groq.com/openai/v1"
TIMEOUT_S = 120.0
MAX_ATTEMPTS = 3
MAX_WAIT_S = 30.0  # longer waits are worse than falling back to the local model


class ReasonerUnavailable(Exception):
    """The hosted model could not answer; use the fallback."""


class GroqClient:
    def __init__(
        self,
        api_key: str,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        reasoning_effort: str = "medium",
    ) -> None:
        self._http = http or httpx.Client(
            base_url=BASE_URL,
            timeout=TIMEOUT_S,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._sleep = sleep
        self._reasoning_effort = reasoning_effort

    def structured[T: BaseModel](
        self,
        model: str,
        output: type[T],
        system: str,
        prompt: str,
        schema: dict[str, Any] | None = None,
        check: Check | None = None,
    ) -> T:
        messages: Messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        body: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "reasoning_effort": self._reasoning_effort,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": output.__name__,
                    "strict": True,
                    "schema": schema or required_schema(output),
                },
            },
        }
        return call_with_retry(
            lambda m: self._complete(body | {"messages": m}), messages, output, check
        )

    def _complete(self, body: dict[str, Any]) -> str:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._http.post("/chat/completions", json=body)
            except httpx.TransportError as error:
                if attempt == MAX_ATTEMPTS:
                    raise ReasonerUnavailable(f"network: {error}") from error
                self._sleep(2.0**attempt)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                wait = _retry_after(response) if response.status_code == 429 else 2.0**attempt
                if attempt == MAX_ATTEMPTS or wait > MAX_WAIT_S:
                    raise ReasonerUnavailable(f"http {response.status_code} after {attempt} tries")
                self._sleep(wait)
                continue

            if _failed_generation(response) and attempt < MAX_ATTEMPTS:
                continue  # the model broke the schema this time; sampling again usually works
            if response.is_error:
                # e.g. 400 json_validate_failed when the model breaks the schema; the
                # local model can still answer, and Groq's reason must reach the record.
                raise ReasonerUnavailable(f"http {response.status_code}: {response.text[:300]}")
            payload: dict[str, Any] = response.json()
            return payload["choices"][0]["message"]["content"]
        raise ReasonerUnavailable("unreachable")  # loop always returns or raises


# Groq's 400 codes for output the model generated but could not fit to the schema.
FAILED_GENERATION = ("json_validate_failed", "output_parse_failed")


def _failed_generation(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False
    try:
        return response.json()["error"]["code"] in FAILED_GENERATION
    except (ValueError, KeyError, TypeError):
        return False


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.headers.get("retry-after", "5"))
    except ValueError:
        return 5.0
