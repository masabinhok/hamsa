"""Validate-and-retry loop shared by every model client (ADR 0006)."""

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

Messages = list[dict[str, Any]]
Send = Callable[[Messages], str]
# Extra validation the schema cannot express; returns an error message or None.
Check = Callable[[Any], str | None]


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


def call_with_retry[T: BaseModel](
    send: Send, messages: Messages, output: type[T], check: Check | None = None
) -> T:
    """Send; on invalid output, show the model the error and retry once."""
    content = send(messages)
    error = _problem(content, output, check)
    if error is None:
        return output.model_validate_json(content)

    retry = [
        *messages,
        {"role": "assistant", "content": content},
        {"role": "user", "content": f"That output is invalid:\n{error}\nReturn corrected JSON."},
    ]
    content = send(retry)
    error = _problem(content, output, check)
    if error is not None:
        raise StructuredOutputError(f"invalid after retry: {error}")
    return output.model_validate_json(content)


def _problem[T: BaseModel](content: str, output: type[T], check: Check | None) -> str | None:
    try:
        parsed = output.model_validate_json(content)
    except ValidationError as error:
        return str(error)
    return check(parsed) if check else None
