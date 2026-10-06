import pytest
from pydantic import ValidationError

from app.pipeline.contracts import (
    RATIONALE_MAX_WORDS,
    Claim,
    Evidence,
    Route,
    RouteDecision,
)
from tests.factories import cite, hit, passage, verdict


def test_model_output_with_unexpected_keys_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Claim.model_validate({"claim": "x", "claim_en": "x", "checkable": True, "guess": "y"})


def test_claim_strips_whitespace_and_rejects_blank_claim() -> None:
    with pytest.raises(ValidationError):
        Claim.model_validate({"claim": "   ", "claim_en": "x", "checkable": True})


def test_archive_hit_needs_at_least_one_score() -> None:
    with pytest.raises(ValidationError, match="phash_distance, a cosine, or both"):
        hit(phash_distance=None, cosine=None)


def test_phash_distance_is_bounded_by_hash_size() -> None:
    with pytest.raises(ValidationError):
        hit(phash_distance=65)


def test_evidence_rejects_duplicate_passage_ids() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Evidence(passages=[passage("p1", "A"), passage("p1", "B")])


def test_evidence_is_capped_at_eight_passages() -> None:
    with pytest.raises(ValidationError):
        Evidence(passages=[passage(f"p{i}", "A") for i in range(9)])


def test_rationale_word_limit() -> None:
    verdict(rationale_en="word " * RATIONALE_MAX_WORDS)
    with pytest.raises(ValidationError, match="limited to"):
        verdict(rationale_en="word " * (RATIONALE_MAX_WORDS + 1))


def test_unknown_citations_lists_ids_not_in_evidence() -> None:
    evidence = Evidence(passages=[passage("p1", "A")])
    v = verdict(citations=[cite("p1"), cite("p9")])
    assert v.unknown_citations(evidence) == ["p9"]


@pytest.mark.parametrize(
    ("route", "merge_into"),
    [(Route.MERGE, None), (Route.HUMAN_REVIEW, "case-1")],
)
def test_merge_into_is_required_for_merge_only(route: Route, merge_into: str | None) -> None:
    with pytest.raises(ValidationError, match="merge_into"):
        RouteDecision(route=route, reasons=["r"], merge_into=merge_into)


def test_route_decision_needs_a_reason() -> None:
    with pytest.raises(ValidationError):
        RouteDecision(route=Route.DISMISS, reasons=[])
