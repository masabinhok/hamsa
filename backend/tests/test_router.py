from dataclasses import replace

import pytest

from app.pipeline.contracts import (
    Duplicate,
    DuplicateBasis,
    Route,
    Stage,
    StageFailure,
    VerdictLabel,
)
from app.router.route import StageOutputs, Thresholds, route
from tests.factories import cite, claim, hit, outputs, passage, verdict

TWO_SOURCES = [passage("p1", "Kathmandu Post"), passage("p2", "Onlinekhabar")]


# precedence of the early rules


def test_stage_failure_goes_to_human_with_every_failure_listed() -> None:
    failures = (
        StageFailure(stage=Stage.EXTRACT, error="invalid json"),
        StageFailure(stage=Stage.RETRIEVE, error="qdrant down"),
    )
    decision = route(StageOutputs(failures=failures))
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == ["extract failed: invalid json", "retrieve failed: qdrant down"]
    assert decision.proposed_label is None


def test_failure_outranks_duplicate() -> None:
    decision = route(
        StageOutputs(
            failures=(StageFailure(stage=Stage.VERDICT, error="timeout"),),
            duplicate=Duplicate(case_id="c-7", basis=DuplicateBasis.MEDIA),
        )
    )
    assert decision.route is Route.HUMAN_REVIEW


def test_duplicate_merges_without_needing_later_stages() -> None:
    decision = route(StageOutputs(duplicate=Duplicate(case_id="c-7", basis=DuplicateBasis.CLAIM)))
    assert decision.route is Route.MERGE
    assert decision.merge_into == "c-7"
    assert decision.reasons == ["same claim as case c-7"]


def test_uncheckable_claim_is_dismissed_without_needing_a_verdict() -> None:
    decision = route(StageOutputs(claim=claim(checkable=False)))
    assert decision.route is Route.DISMISS


@pytest.mark.parametrize("missing", ["claim", "media_match", "evidence", "verdict"])
def test_missing_output_without_recorded_failure_is_a_bug(missing: str) -> None:
    with pytest.raises(ValueError, match=f"{missing} is missing"):
        route(replace(outputs(), **{missing: None}))


def test_hallucinated_citation_reaching_the_router_is_a_bug() -> None:
    with pytest.raises(ValueError, match="not given"):
        route(outputs(verdict=verdict(citations=[cite("p99")])))


# recycled media


def test_strong_prior_match_with_false_verdict_is_fast_tracked() -> None:
    decision = route(outputs(hits=[hit()], verdict=verdict("false", confidence=0.3)))
    assert decision.route is Route.FAST_TRACK
    assert decision.reasons == ["recycled media: matches 2023 Himachal Pradesh floods, Kullu"]
    assert decision.proposed_label is VerdictLabel.FALSE


@pytest.mark.parametrize(
    ("phash_distance", "cosine", "strong"),
    [
        (16, None, True),
        (17, None, False),
        (None, 0.97, True),
        (None, 0.9699, False),
        (30, 0.98, True),
        # Measured: a different photo of the same river. Must never count as recycled.
        (26, 0.946, False),
    ],
)
def test_match_strength_boundaries(
    phash_distance: int | None, cosine: float | None, strong: bool
) -> None:
    h = hit(phash_distance=phash_distance, cosine=cosine)
    decision = route(outputs(hits=[h], verdict=verdict("misleading", confidence=0.3)))
    assert (decision.route is Route.FAST_TRACK) is strong


def test_verified_genuine_match_is_not_recycled_evidence() -> None:
    genuine = hit(archive_label="verified_genuine", original_context="NDRRMA footage, 2026-08-27")
    decision = route(outputs(hits=[genuine], verdict=verdict("false", confidence=0.3)))
    assert decision.route is Route.HUMAN_REVIEW


def test_recycled_media_with_true_verdict_is_a_conflict() -> None:
    decision = route(outputs(hits=[hit()], verdict=verdict("true", confidence=0.99)))
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == [
        "verdict is true but media matches 2023 Himachal Pradesh floods, Kullu"
    ]


# ai-tool watermarks


def test_ai_watermark_with_confident_false_verdict_is_fast_tracked() -> None:
    decision = route(
        outputs(claim=claim(watermarks=["Made with Google Veo 3"]), verdict=verdict("false", 0.9))
    )
    assert decision.route is Route.FAST_TRACK
    assert decision.reasons == ["visible ai-tool watermark: veo"]


def test_ai_watermark_with_low_confidence_goes_to_human() -> None:
    decision = route(outputs(claim=claim(watermarks=["Sora"]), verdict=verdict("false", 0.6)))
    assert decision.route is Route.HUMAN_REVIEW


def test_non_ai_watermark_is_not_a_signal() -> None:
    decision = route(
        outputs(claim=claim(watermarks=["Kantipur TV"]), verdict=verdict("false", 0.9))
    )
    assert decision.route is Route.HUMAN_REVIEW


def test_ai_watermark_with_true_verdict_is_a_conflict() -> None:
    decision = route(
        outputs(
            claim=claim(watermarks=["SORA @someone"]),
            passages=TWO_SOURCES,
            verdict=verdict(
                "true", 0.95, citations=[cite("p1", "supports"), cite("p2", "supports")]
            ),
        )
    )
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == ["verdict is true but ai-tool watermark visible: sora"]


# evidence


@pytest.mark.parametrize("label", ["false", "misleading"])
def test_two_independent_refuting_sources_fast_track(label: str) -> None:
    decision = route(
        outputs(
            passages=TWO_SOURCES,
            verdict=verdict(label, 0.85, citations=[cite("p1"), cite("p2")]),
        )
    )
    assert decision.route is Route.FAST_TRACK
    assert decision.reasons == [
        "strong evidence: 2 independent sources (Kathmandu Post, Onlinekhabar)"
    ]


def test_true_verdict_needs_supporting_sources() -> None:
    citations = [cite("p1", "supports"), cite("p2", "supports")]
    decision = route(
        outputs(passages=TWO_SOURCES, verdict=verdict("true", 0.9, citations=citations))
    )
    assert decision.route is Route.FAST_TRACK
    assert decision.proposed_label is VerdictLabel.TRUE


def test_two_passages_from_one_source_count_once() -> None:
    same_outlet = [passage("p1", "Kathmandu Post"), passage("p2", "Kathmandu Post")]
    decision = route(
        outputs(
            passages=same_outlet, verdict=verdict("false", 0.95, citations=[cite("p1"), cite("p2")])
        )
    )
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == ["ambiguous: 1 independent source(s), 2 needed to fast-track"]


def test_confidence_just_below_threshold_goes_to_human() -> None:
    decision = route(
        outputs(
            passages=TWO_SOURCES,
            verdict=verdict("false", 0.849, citations=[cite("p1"), cite("p2")]),
        )
    )
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == ["ambiguous: confidence 0.849 below 0.85"]


def test_cited_source_disagreeing_with_verdict_is_a_conflict() -> None:
    three = [*TWO_SOURCES, passage("p3", "Nepal Factcheck", source_kind="fact_check")]
    citations = [cite("p1"), cite("p2"), cite("p3", "supports")]
    decision = route(outputs(passages=three, verdict=verdict("false", 0.99, citations=citations)))
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == ["cited Nepal Factcheck supports the claim"]


def test_unverifiable_is_never_fast_tracked() -> None:
    decision = route(
        outputs(
            hits=[hit()],
            passages=TWO_SOURCES,
            verdict=verdict("unverifiable", 0.99, citations=[cite("p1"), cite("p2")]),
        )
    )
    assert decision.route is Route.HUMAN_REVIEW
    assert decision.reasons == ["ambiguous: evidence does not settle the claim"]


# new claims


def test_no_evidence_and_no_archive_match_is_investigated() -> None:
    decision = route(outputs(passages=[]))
    assert decision.route is Route.INVESTIGATE
    assert decision.reasons == ["new claim: no evidence and no archive match"]


def test_weak_archive_match_alone_is_not_a_new_claim() -> None:
    assert route(outputs(hits=[hit(phash_distance=40)], passages=[])).route is Route.HUMAN_REVIEW


# thresholds


def test_custom_thresholds_are_respected() -> None:
    case = outputs(
        passages=TWO_SOURCES,
        verdict=verdict("false", 0.7, citations=[cite("p1"), cite("p2")]),
    )
    assert route(case).route is Route.HUMAN_REVIEW
    assert route(case, Thresholds(fast_track_confidence=0.7)).route is Route.FAST_TRACK
