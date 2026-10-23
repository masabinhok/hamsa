from pathlib import Path

from app.eval.live import LiveRow, load_rows, summarize
from tests.factories import cite, outputs, passage, verdict

BATCH = """# Live batch

## False or misleading (rated by a fact-checker)

| # | Link | Platform | Expected | Source |
|---|---|---|---|---|
| L01 | https://www.instagram.com/reel/A/ | Instagram | misleading | BOOM |

## True (footage published by an established outlet)

| # | Link | Outlet |
|---|---|---|
| L02 | https://youtu.be/x | CNA |

## Unverifiable, or the checker's call

| # | Link | Note |
|---|---|---|
| L03 | https://x.com/a/status/1 | **unverifiable**: no source |
| L04 | https://x.com/a/status/2 | the checker decides |
"""


def test_rows_take_their_label_from_the_section(tmp_path: Path) -> None:
    batch = tmp_path / "batch-01.md"
    batch.write_text(BATCH, encoding="utf-8")
    assert load_rows([batch]) == [
        LiveRow("L01", "https://www.instagram.com/reel/A/", "misleading"),
        LiveRow("L02", "https://youtu.be/x", "true"),
        LiveRow("L03", "https://x.com/a/status/1", "unverifiable"),
        LiveRow("L04", "https://x.com/a/status/2", None),
    ]


def test_a_refuting_fast_track_counts_as_right_and_a_human_is_always_safe() -> None:
    fact_check = [passage("p1", "Nepal Factcheck", source_kind="fact_check")]
    false = outputs(passages=fact_check, verdict=verdict("false", 0.9, citations=[cite("p1")]))
    unsure = outputs(verdict=verdict("unverifiable", 0.5))
    row = LiveRow("L01", "https://x.com/a/status/1", "misleading")
    lines = summarize([(row, "misleading", false), (row, "true", unsure)])
    assert "fast-track precision: 1/1 (100%) (target 95%)" in lines
    assert "sent to a human: 1/2 (50%)" in lines
