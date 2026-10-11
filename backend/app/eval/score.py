"""Score the pipeline against the eval set, from backend/:

    uv run python -m app.eval.score [--split tune|test|all] [--no-fact-checks] [--fresh]

Stage outputs are cached per item in data/eval/runs/<run>/, and only the router reruns at
scoring time, so tuning `Thresholds` costs no model calls. `--fresh` reruns the pipeline.
Tune on h001-h040; report final numbers on h041 onward (docs/data-collection.md).
"""

import argparse
import json
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.config import REPO_ROOT, get_settings
from app.eval.dataset import EvalItem, MediaKind, Tactic, Verdict, load_items
from app.pipeline.__main__ import build_pipeline
from app.pipeline.contracts import Route, RouteDecision, SourceKind, VerdictLabel
from app.pipeline.retrieve import EvidenceStore
from app.pipeline.run import run
from app.router.route import DEFAULT_THRESHOLDS, StageOutputs, Thresholds, recycled_hits, route
from app.store.cases import outputs_from_json, outputs_to_json

EVAL_DIR = REPO_ROOT / "data" / "eval"
RUNS_DIR = EVAL_DIR / "runs"
TUNE_LAST = 40
REFUTED = (VerdictLabel.FALSE, VerdictLabel.MISLEADING)
TO_HUMAN = (Route.HUMAN_REVIEW, Route.INVESTIGATE)


@dataclass(frozen=True)
class Scored:
    item: EvalItem
    outputs: StageOutputs
    seconds: float


class WithoutFactChecks(EvidenceStore):
    """Simulates a post nobody has debunked yet."""

    def search(self, vector: list[float], since: date) -> list[dict[str, Any]]:
        # shortcut: filters after the candidate limit, so fewer passages reach the reranker;
        # fine for an ablation, query with a must_not filter if this becomes a headline number.
        kept = super().search(vector, since)
        return [p for p in kept if p.get("source_kind") != SourceKind.FACT_CHECK.value]


def in_split(item: EvalItem, split: str) -> bool:
    number = int(item.id[1:])
    return split == "all" or (number <= TUNE_LAST) == (split == "tune")


def _refuted(label: VerdictLabel | Verdict | None) -> bool:
    return label is not None and label.value in {r.value for r in REFUTED}


def _correct(item: EvalItem, decision: RouteDecision) -> bool:
    """Exact label, or both refuting: false versus misleading is a publisher's choice."""
    label = decision.proposed_label
    if label is None:
        return False
    return label.value == item.verdict.value or (_refuted(item.verdict) and _refuted(label))


def _ratio(hits: int, total: int) -> str:
    return f"{hits}/{total} ({hits / total:.0%})" if total else "n/a"


def summarize(rows: Sequence[Scored], t: Thresholds = DEFAULT_THRESHOLDS) -> list[str]:
    decisions = [route(row.outputs, t) for row in rows]
    pairs = list(zip(rows, decisions, strict=True))

    exact = sum(
        d.proposed_label is not None and d.proposed_label.value == r.item.verdict.value
        for r, d in pairs
    )
    refuted = sum(_refuted(r.item.verdict) == _refuted(d.proposed_label) for r, d in pairs)

    media = [
        (r, bool(recycled_hits(r.outputs, t))) for r in rows if r.item.kind is not MediaKind.TEXT
    ]
    truly = [found for r, found in media if r.item.tactic is Tactic.RECYCLED]
    flagged = [r for r, found in media if found]
    true_positives = sum(truly)

    fast = [(r, d) for r, d in pairs if d.route is Route.FAST_TRACK]
    fast_correct = sum(_correct(r.item, d) for r, d in fast)
    to_human = sum(d.route in TO_HUMAN for d in decisions)

    seconds = sorted(r.seconds for r in rows)
    p50, p95 = (
        (statistics.median(seconds), statistics.quantiles(seconds, n=20, method="inclusive")[18])
        if len(seconds) >= 2
        else (seconds[0], seconds[0])
        if seconds
        else (0.0, 0.0)
    )

    lines = [
        f"items: {len(rows)}",
        f"verdict exact agreement: {_ratio(exact, len(rows))}",
        f"refuted-or-not agreement: {_ratio(refuted, len(rows))}",
        f"recycled media precision: {_ratio(true_positives, len(flagged))}",
        f"recycled media recall: {_ratio(true_positives, len(truly))}",
        f"fast-track precision: {_ratio(fast_correct, len(fast))} (target 95%)",
        f"sent to a human: {_ratio(to_human, len(rows))}",
        f"latency: p50 {p50:.1f} s, p95 {p95:.1f} s",
        "",
        # safe: fast-tracked with the right label, or left to a human.
        "| item | truth | proposed | route | safe |",
        "|---|---|---|---|---|",
    ]
    for r, d in pairs:
        safe = _correct(r.item, d) if d.route is Route.FAST_TRACK else d.route in TO_HUMAN
        label = d.proposed_label.value if d.proposed_label else "-"
        mark = "yes" if safe else "**no**"
        lines.append(
            f"| {r.item.id} | {r.item.verdict.value} | {label} | {d.route.value} | {mark} |"
        )
    return lines


def _load(path: Path, item: EvalItem) -> Scored:
    data = json.loads(path.read_text(encoding="utf-8"))
    outputs = replace(outputs_from_json(data["outputs"]), seen_on=item.posted_on)
    return Scored(item=item, outputs=outputs, seconds=data["seconds"])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.eval.score")
    parser.add_argument("--split", choices=("tune", "test", "all"), default="tune")
    parser.add_argument("--no-fact-checks", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="rerun the pipeline")
    args = parser.parse_args(argv)

    items = [
        i for i in load_items(EVAL_DIR / "items.csv", EVAL_DIR / "media") if in_split(i, args.split)
    ]
    run_dir = RUNS_DIR / ("no-fact-checks" if args.no_fact_checks else "default")
    run_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    pipeline = None
    rows: list[Scored] = []
    for item in items:
        cached = run_dir / f"{item.id}.json"
        if args.fresh or not cached.is_file():
            if pipeline is None:
                pipeline = build_pipeline(settings)
                if args.no_fact_checks:
                    store = WithoutFactChecks(QdrantClient(url=str(settings.qdrant_url)))
                    pipeline = replace(pipeline, evidence=store)
            media = [EVAL_DIR / "media" / item.media_file] if item.media_file else []
            result = run(pipeline, item.claim_text, media, seen_on=item.posted_on)
            payload = {
                "outputs": outputs_to_json(result.outputs),
                "seconds": round(sum(result.seconds.values()), 2),
            }
            cached.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  ran {item.id}: {result.decision.route.value}", flush=True)
        rows.append(_load(cached, item))

    lines = summarize(rows)
    (run_dir / f"report-{args.split}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
