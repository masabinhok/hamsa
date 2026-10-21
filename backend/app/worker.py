"""The pipeline worker: `uv run python -m app.worker` from backend/ (ADR 0005).

One process, one job at a time, which also keeps the GPU to one model job at a time.
"""

import logging
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import timedelta
from functools import partial
from pathlib import Path

from sqlalchemy import select

from app.api.main import sniff_suffix
from app.config import get_settings
from app.ingest.download import Downloaded, download
from app.learn import Verdicted, teach
from app.pipeline.contracts import (
    Duplicate,
    DuplicateBasis,
    Route,
    RouteDecision,
    VerdictLabel,
)
from app.pipeline.run import Result
from app.router.route import StageOutputs, route
from app.store.cases import (
    Database,
    StoredMedia,
    claim_job,
    complete_job,
    media_duplicate,
    open_claims,
    requeue_job,
    save_media,
)
from app.store.models import Case, Job, Lesson, Media, utcnow

MAX_ATTEMPTS = 3
MAX_CAPTION_CHARS = 5000  # the same limit as submitted text (MAX_TEXT_CHARS in the API)
SENDER_NOTE = "Sender's note: "  # the extraction prompt reads text after this as context
BACKOFF = (timedelta(seconds=30), timedelta(minutes=2))
POLL_S = 1.0

Runner = Callable[[str | None, Sequence[Path]], Result]
Fetch = Callable[[str, Path], Downloaded]
Teach = Callable[[Verdicted], list[str]]
log = logging.getLogger("hamsa.worker")


def attach_link_media(db: Database, case_id: str, media_root: Path, fetch: Fetch) -> None:
    """Download the media behind a pasted link, so a link is checked like an upload.

    On failure the case goes on with its text; the public page asks for the file.
    """
    with db.session() as session:
        case = session.get_one(Case, case_id)
        url = case.source_url if not case.media else None
    if url is None:
        return
    with tempfile.TemporaryDirectory() as tmp:
        try:
            post = fetch(url, Path(tmp))
        except (subprocess.SubprocessError, OSError) as error:
            stderr = getattr(error, "stderr", None) or ""
            reason = stderr.strip().splitlines()[-1] if stderr.strip() else type(error).__name__
            log.warning("case %s: could not fetch %s: %s", case_id, url, reason)
            return
        stored: list[StoredMedia] = []
        for file in post.files:
            data = file.read_bytes()
            if suffix := sniff_suffix(data):  # only the types an upload may have
                stored.append(save_media(media_root, case_id, data, suffix))
    with db.session.begin() as session:
        case = session.get_one(Case, case_id)
        case.media.extend(
            Media(filename=m.filename, sha256=m.sha256, size_bytes=m.size_bytes) for m in stored
        )
        if post.caption:
            caption = post.caption[:MAX_CAPTION_CHARS]
            # The caption is what the post claims; the sender's words only frame it.
            case.text = f"{caption}\n\n{SENDER_NOTE}{case.text}" if case.text else caption
    log.info("case %s: fetched %d file(s) from the link", case_id, len(stored))


def process_next(
    db: Database, runner: Runner, media_root: Path, fetch: Fetch | None = None
) -> str | None:
    """Run the oldest due job. Returns its case id, or None if there was nothing to do."""
    with db.session.begin() as session:
        claimed = claim_job(session)
    if claimed is None:
        return None
    job_id, case_id = claimed
    if fetch is not None:
        attach_link_media(db, case_id, media_root, fetch)

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


def learn_next(db: Database, media_root: Path, site_url: str, teach: Teach) -> bool:
    """Teach the archive from the oldest pending published verdict. False if none waits."""
    with db.session() as session:
        lesson = session.scalars(
            select(Lesson)
            .where(Lesson.done_at.is_(None), Lesson.error.is_(None))
            .order_by(Lesson.id)
            .limit(1)
        ).first()
        if lesson is None:
            return False
        case = session.get_one(Case, lesson.case_id)
        verdicted = Verdicted(
            case_id=case.id,
            label=VerdictLabel(case.final_label),
            rationale_en=case.final_rationale_en or "",
            reported_on=case.created_at.date(),
            media=[media_root / case.id / m.filename for m in case.media],
            page_url=case.source_url or f"{site_url}/check/{case.id}",
            original_url=lesson.original_url,
        )
        lesson_id = lesson.id

    error = None
    try:
        added = teach(verdicted)
        log.info("case %s taught the archive: %s", verdicted.case_id, added or "nothing new")
    except Exception as failure:  # one bad lesson (a dead link) must not stop the worker
        log.exception("case %s: lesson failed", verdicted.case_id)
        error = f"{type(failure).__name__}: {failure}"[:500]
    with db.session.begin() as session:
        done = session.get_one(Lesson, lesson_id)
        done.done_at, done.error = (utcnow(), None) if error is None else (None, error)
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = get_settings()
    db = Database(settings.database_url)
    db.create_all()

    # Imported here: building the pipeline loads torch and opens model clients.
    from app.pipeline.__main__ import build_pipeline
    from app.pipeline.run import run

    pipeline = build_pipeline(settings)
    fetch = partial(download, browser=settings.fetch_browser)

    def lesson(verdicted: Verdicted) -> list[str]:
        return teach(verdicted, pipeline.archive, pipeline.embed_image, fetch)

    def runner(text: str | None, media: Sequence[Path]) -> Result:
        # The case being run is PROCESSING, so the routed cases never include itself.
        with db.session() as session:
            waiting = open_claims(session)
        return run(pipeline, text, media, open_claims=waiting)

    log.info("worker ready")
    try:
        while True:
            idle = process_next(db, runner, settings.media_root, fetch) is None
            if idle and not learn_next(db, settings.media_root, settings.frontend_origin, lesson):
                time.sleep(POLL_S)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
