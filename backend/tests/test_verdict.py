from typing import Any

import pytest
from pydantic import BaseModel

from app.llm.groq import ReasonerUnavailable
from app.llm.structured import Check, StructuredOutputError
from app.pipeline.contracts import Evidence, MediaMatch, Stance, VerdictLabel
from app.pipeline.verdict import (
    build_prompt,
    draft_schema,
    judge,
)
from tests.factories import claim, hit, passage

EVIDENCE = Evidence(
    passages=[
        passage("a1b2c3-0", "Nepal Factcheck", source_kind="fact_check"),
        passage("d4e5f6-2", "Onlinekhabar"),
    ]
)


def draft(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "label": "false",
        "confidence": 0.9,
        "rationale_en": "The video is from Alaska.",
        "rationale_ne": "भिडियो अलास्काको हो।",
        "citations": [{"evidence": "E1", "stance": "refutes"}],
    }
    return fields | overrides


class FakeReasoner:
    """Replays drafts through the caller's check, as the real clients do."""

    def __init__(self, *outcomes: dict[str, Any] | Exception) -> None:
        self.outcomes = list(outcomes)
        self.schemas: list[dict[str, Any] | None] = []
        self.prompts: list[str] = []

    def structured[T: BaseModel](
        self,
        model: str,
        output: type[T],
        system: str,
        prompt: str,
        *,
        schema: dict[str, Any] | None = None,
        check: Check | None = None,
    ) -> T:
        self.schemas.append(schema)
        self.prompts.append(prompt)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        parsed = output.model_validate(outcome)
        if check and (problem := check(parsed)):
            raise StructuredOutputError(problem)
        return parsed


def test_schema_allows_only_the_given_evidence_labels() -> None:
    schema = draft_schema(["E1", "E2"])
    assert schema["$defs"]["DraftCitation"]["properties"]["evidence"]["enum"] == ["E1", "E2"]


def test_schema_forbids_citations_when_there_is_no_evidence() -> None:
    assert draft_schema([])["properties"]["citations"]["maxItems"] == 0


def test_prompt_labels_evidence_and_states_media_and_match_strength() -> None:
    prompt = build_prompt(
        claim(), MediaMatch(hits=[hit(phash_distance=3)]), EVIDENCE, has_media=True
    )
    assert prompt.startswith("POST: text with images or video")
    assert "- strong match to prior footage: 2023 Himachal Pradesh floods, Kullu" in prompt
    assert "[E1] Nepal Factcheck (fact_check, " in prompt
    assert "[E2] Onlinekhabar (news, " in prompt


def test_prompt_shows_passage_headlines() -> None:
    headlined = Evidence(
        passages=[passage("x-0", "Nepal Factcheck", title="Viral video is from Alaska")]
    )
    prompt = build_prompt(claim(), MediaMatch(), headlined, has_media=True)
    assert "[E1] Nepal Factcheck (news, " in prompt
    assert "Headline: Viral video is from Alaska\n" in prompt


def test_text_only_post_and_empty_inputs_are_stated() -> None:
    prompt = build_prompt(claim(), MediaMatch(), Evidence(), has_media=False)
    assert prompt.startswith("POST: text only")
    assert "ARCHIVE MATCHES:\nnone" in prompt
    assert "EVIDENCE:\nnone found" in prompt


def test_citation_labels_map_back_to_passage_ids() -> None:
    reasoner = FakeReasoner(
        draft(
            citations=[
                {"evidence": "E2", "stance": "refutes"},
                {"evidence": "E1", "stance": "supports"},
            ]
        )
    )
    verdict = judge(claim(), MediaMatch(), EVIDENCE, [(reasoner, "gpt-oss")], has_media=False)

    assert verdict.label is VerdictLabel.FALSE
    assert [(c.passage_id, c.stance) for c in verdict.citations] == [
        ("d4e5f6-2", Stance.REFUTES),
        ("a1b2c3-0", Stance.SUPPORTS),
    ]
    assert verdict.model == "gpt-oss"
    assert verdict.fallback is False


def test_unknown_citation_label_is_rejected_by_the_check() -> None:
    reasoner = FakeReasoner(draft(citations=[{"evidence": "E9", "stance": "refutes"}]))
    with pytest.raises(StructuredOutputError, match="E9"):
        judge(claim(), MediaMatch(), EVIDENCE, [(reasoner, "gpt-oss")], has_media=False)


def test_overlong_rationale_is_rejected_by_the_check() -> None:
    reasoner = FakeReasoner(draft(rationale_en="word " * 121))
    with pytest.raises(StructuredOutputError, match="exceeds"):
        judge(claim(), MediaMatch(), EVIDENCE, [(reasoner, "gpt-oss")], has_media=False)


def test_falls_back_to_the_local_model_and_marks_the_verdict() -> None:
    primary = FakeReasoner(ReasonerUnavailable("http 429 after 1 tries"))
    local = FakeReasoner(draft())

    verdict = judge(
        claim(),
        MediaMatch(),
        EVIDENCE,
        [(primary, "gpt-oss"), (local, "qwen3-vl")],
        has_media=False,
    )

    assert verdict.model == "qwen3-vl"
    assert verdict.fallback is True
    assert local.prompts == primary.prompts


def test_every_reasoner_failing_raises_with_each_reason() -> None:
    primary = FakeReasoner(ReasonerUnavailable("http 429"))
    local = FakeReasoner(StructuredOutputError("invalid after retry"))
    with pytest.raises(StructuredOutputError, match="gpt-oss: http 429; qwen3-vl: invalid"):
        judge(
            claim(),
            MediaMatch(),
            EVIDENCE,
            [(primary, "gpt-oss"), (local, "qwen3-vl")],
            has_media=False,
        )
