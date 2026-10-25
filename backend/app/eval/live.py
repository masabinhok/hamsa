"""Score real posts sent to Hamsa against their labels, from backend/:

    uv run python -m app.eval.live [--fresh]

Rows come from data/eval/live/batch-*.md, matched to their case by link. Ground truth is
the label a checker published on the desk, else the row's expected label; rows left to
"the checker's call" count only once published. Without --fresh, each case is scored on
the stage outputs the worker stored (rerouted by today's router); --fresh reruns the
pipeline on the case's text and media and caches it in data/eval/runs/live/.
"""

import argparse
import json
import re
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.config import get_settings
from app.eval.score import EVAL_DIR, PACE_S, RUNS_DIR, TO_HUMAN, is_refuted, ratio
from app.pipeline.__main__ import build_pipeline
from app.pipeline.contracts import Route, VerdictLabel
from app.pipeline.run import run
from app.router.route import StageOutputs, route
from app.store.cases import Database, normalize_url, outputs_from_json, outputs_to_json
from app.store.models import Case, CaseStatus

LABELS = tuple(label.value for label in VerdictLabel)


@dataclass(frozen=True)
class LiveRow:
    id: str
    url: str
    expected: str | None  # None: the checker's call


def load_rows(paths: Sequence[Path]) -> list[LiveRow]:
    rows: list[LiveRow] = []
    for path in paths:
        section = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                section = line[3:].lower()
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not re.fullmatch(r"L\d+", cells[0]) or len(cells) < 2:
                continue
            if section.startswith("true"):
                expected: str | None = VerdictLabel.TRUE.value
            elif section.startswith("false"):
                expected = next(c for c in cells if c in LABELS)
            else:
                expected = "unverifiable" if "**unverifiable**" in line else None
            rows.append(LiveRow(cells[0], cells[1], expected))
    return rows


def summarize(scored: Sequence[tuple[LiveRow, str, StageOutputs]]) -> list[str]:
    decisions = [route(outputs) for _, _, outputs in scored]
    pairs = list(zip(scored, decisions, strict=True))
    exact = sum(
        d.proposed_label is not None and d.proposed_label.value == t for (_, t, _), d in pairs
    )
    refuted = sum(
        is_refuted(VerdictLabel(t)) == is_refuted(d.proposed_label) for (_, t, _), d in pairs
    )
    fast = [(t, d) for (_, t, _), d in pairs if d.route is Route.FAST_TRACK]
    fast_ok = sum(_right(t, d.proposed_label) for t, d in fast)
    lines = [
        f"items: {len(scored)}",
        f"verdict exact agreement: {ratio(exact, len(scored))}",
        f"refuted-or-not agreement: {ratio(refuted, len(scored))}",
        f"fast-track precision: {ratio(fast_ok, len(fast))} (target 95%)",
        f"sent to a human: {ratio(sum(d.route in TO_HUMAN for d in decisions), len(scored))}",
        "",
        "| item | truth | proposed | route | safe | reason |",
        "|---|---|---|---|---|---|",
    ]
    for (row, truth, _), d in pairs:
        proposed = d.proposed_label.value if d.proposed_label else "-"
        safe = (
            _right(truth, d.proposed_label) if d.route is Route.FAST_TRACK else d.route in TO_HUMAN
        )
        reason = (d.reasons[0] if d.reasons else "")[:90].replace("|", "/")
        mark = "yes" if safe else "**no**"
        lines.append(f"| {row.id} | {truth} | {proposed} | {d.route.value} | {mark} | {reason} |")
    return lines


def _right(truth: str, label: VerdictLabel | None) -> bool:
    """Exact label, or both refuting: false versus misleading is a publisher's choice."""
    return label is not None and (
        label.value == truth or (is_refuted(VerdictLabel(truth)) and is_refuted(label))
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval.live")
    parser.add_argument("--fresh", action="store_true", help="rerun the pipeline")
    args = parser.parse_args(argv)

    settings = get_settings()
    db = Database(settings.database_url)
    run_dir = RUNS_DIR / "live"
    run_dir.mkdir(parents=True, exist_ok=True)
    media_root = Path(settings.database_url.removeprefix("sqlite:///")).parent / "cases"
    pipeline = None
    scored: list[tuple[LiveRow, str, StageOutputs]] = []
    skipped: list[str] = []

    with db.session() as session:
        linked = session.scalars(
            select(Case).where(Case.source_url.is_not(None)).order_by(Case.created_at)
        ).all()
        by_link: dict[str, Case] = {}
        for case in linked:
            by_link.setdefault(normalize_url(case.source_url or ""), case)

        for row in load_rows(sorted((EVAL_DIR / "live").glob("batch-*.md"))):
            case = by_link.get(normalize_url(row.url))
            published = case.final_label if case and case.status is CaseStatus.PUBLISHED else None
            truth = published or row.expected
            if case is None or truth is None or not case.outputs:
                skipped.append(f"{row.id} ({'not sent' if case is None else 'no label'})")
                continue
            stored = outputs_from_json(case.outputs)
            cached = run_dir / f"{row.id}.json"
            if args.fresh or cached.is_file():
                if args.fresh:
                    if pipeline is None:
                        pipeline = build_pipeline(settings)
                    media = (
                        sorted((media_root / case.id).iterdir())
                        if (media_root / case.id).is_dir()
                        else []
                    )
                    result = run(
                        pipeline,
                        case.text,
                        media,
                        seen_on=stored.posted_on,
                        source_url=case.source_url,
                    )
                    cached.write_text(
                        json.dumps(outputs_to_json(result.outputs), ensure_ascii=False),
                        encoding="utf-8",
                    )
                    print(f"  ran {row.id}: {result.decision.route.value}", flush=True)
                    time.sleep(PACE_S)
                stored = outputs_from_json(json.loads(cached.read_text(encoding="utf-8")))
            scored.append((row, truth, stored))

    lines = summarize(scored)
    if skipped:
        lines += ["", f"skipped: {', '.join(skipped)}"]
    (run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
