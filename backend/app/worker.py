"""The pipeline worker: `uv run python -m app.worker` from backend/ (ADR 0005).

One process, one job at a time, which also keeps the GPU to one model job at a time.
"""

import logging
import sys
import time
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path

from app.config import get_settings
from app.pipeline.contracts import Duplicate, DuplicateBasis, Route, RouteDecision
from app.pipeline.run import Result
from app.router.route import StageOutputs, route
from app.store.cases import (
    Database,
    claim_job,
    complete_job,
    media_duplicate,
    open_claims,
    requeue_job,
)
from app.store.models import Case, Job

MAX_ATTEMPTS = 3
BACKOFF = (timedelta(seconds=30), timedelta(minutes=2))
POLL_S = 1.0

Runner = Callable[[str | None, Sequence[Path]], Result]
log = logging.getLogger("hamsa.worker")


def process_next(db: Database, runner: Runner, media_root: Path) -> str | None:
    """Run the oldest due job. Returns its case id, or None if there was nothing to do."""
    with db.session.begin() as session:
        claimed = claim_job(session)
    if claimed is None:
        return None
    job_id, case_id = claimed

    with db.session() as session:
        case = session.get_one(Case, case_id)
        text = case.text
        paths = [media_root / case_id / m.filename for m in case.media]
        original = media_duplicate(session, case)

    if original is not None:
        # The same file is already on the desk: merge without spending any model time.
        same = StageOutputs(duplicate=Duplicate(case_id=original, basis=DuplicateBasis.MEDIA))
        result = Result(outputs=same, decision=route(same))
    else:
        try:
            result = runner(text, paths)
        except Exception as error:  # a pipeline bug must not loop forever or lose the case
            log.exception("case %s: pipeline error", case_id)
            result = Result(
                outputs=StageOutputs(),
                decision=RouteDecision(
                    route=Route.HUMAN_REVIEW, reasons=[f"pipeline error: {type(error).__name__}"]
                ),
            )

    with db.session.begin() as session:
        job = session.get_one(Job, job_id)
        case = session.get_one(Case, case_id)
        transient = [f for f in result.outputs.failures if f.transient]
        if transient and job.attempts < MAX_ATTEMPTS:
            delay = BACKOFF[min(job.attempts, len(BACKOFF)) - 1]
            requeue_job(session, job_id, "; ".join(f.error for f in transient), delay)
            log.warning("case %s: transient failure, retry in %s", case_id, delay)
        else:
            complete_job(session, job_id, case, result.outputs, result.decision, result.seconds)
            log.info("case %s: %s %s", case_id, result.decision.route, result.seconds)
    return case_id


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    db = Database(settings.database_url)
    db.create_all()

    # Imported here: building the pipeline loads torch and opens model clients.
    from app.pipeline.__main__ import build_pipeline
    from app.pipeline.run import run

    pipeline = build_pipeline(settings)

    def runner(text: str | None, media: Sequence[Path]) -> Result:
        # The case being run is PROCESSING, so the routed cases never include itself.
        with db.session() as session:
            waiting = open_claims(session)
        return run(pipeline, text, media, open_claims=waiting)

    log.info("worker ready")
    try:
        while True:
            if process_next(db, runner, settings.media_root) is None:
                time.sleep(POLL_S)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
