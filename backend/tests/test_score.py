from datetime import date
from typing import Any

from app.eval.dataset import EvalItem
from app.eval.score import Scored, in_split, summarize
from tests.factories import cite, claim, hit, outputs, passage, verdict


def item(id_: str, label: str, tactic: str, **overrides: Any) -> EvalItem:
    fields: dict[str, Any] = {
        "id": id_,
        "kind": "video",
        "platform": "facebook",
        "language": "ne",
        "claim_text": "मेलम्ची बजार बगायो",
        "media_file": f"{id_}.mp4",
        "verdict": label,
        "tactic": tactic,
        "fact_check_url": "https://nepalfactcheck.org/x",
    }
    if tactic == "recycled":
        fields |= {"original_source_url": "https://youtu.be/o", "original_context": "Kullu 2023"}
    return EvalItem.model_validate(fields | overrides)


def test_split_boundary_is_h040() -> None:
    assert in_split(item("h040", "true", "none"), "tune")
    assert in_split(item("h041", "true", "none"), "test")
    assert not in_split(item("h041", "true", "none"), "tune")


def test_summary_counts_each_metric() -> None:
    fact_check = passage("p1", "Nepal Factcheck", source_kind="fact_check")
    rows = [
        # Recycled, matched, fast-tracked as misleading against a published "false": correct.
        Scored(
            item("h001", "false", "recycled"),
            outputs(hits=[hit()], verdict=verdict("misleading", 0.3)),
            10.0,
        ),
        # Recycled but not matched; low confidence, so a human sees it.
        Scored(item("h002", "misleading", "recycled"), outputs(), 20.0),
        # True post wrongly fast-tracked as false by a confident fact-check citation.
        Scored(
            item("h003", "true", "none"),
            outputs(
                passages=[fact_check],
                verdict=verdict("false", 0.95, citations=[cite("p1")]),
            ),
            30.0,
        ),
        # Old genuine footage under a new claim counts as recycled, by date.
        Scored(
            item("h004", "false", "recycled"),
            outputs(
                claim=claim(),
                hits=[hit(archive_label="verified_genuine", original_date=date(2021, 6, 15))],
                verdict=verdict("false", 0.3),
                seen_on=date(2026, 8, 30),
            ),
            40.0,
        ),
    ]

    lines = summarize(rows)

    assert lines[:8] == [
        "items: 4",
        "verdict exact agreement: 1/4 (25%)",
        "refuted-or-not agreement: 3/4 (75%)",
        "recycled media precision: 2/2 (100%)",
        "recycled media recall: 2/3 (67%)",
        "fast-track precision: 2/3 (67%) (target 95%)",
        "sent to a human: 1/4 (25%)",
        "latency: p50 25.0 s, p95 38.5 s",
    ]
    assert "| h003 | true | false | fast_track | **no** |" in lines
