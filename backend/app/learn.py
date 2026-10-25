"""Teach the archive from published verdicts (ADR 0011).

The archive is not collected in advance. Every published verdict adds to it, so the next
repost of the same footage is matched without a checker:
- a post published as true becomes genuine footage of that date;
- a post published as false or misleading becomes known debunked footage;
- the original a checker found (e.g. with Google Lens) becomes the earlier footage it is.
"""

import hashlib
import re
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from app import archive
from app.ingest.download import Downloaded
from app.ingest.frames import frames_of
from app.pipeline.contracts import ArchiveLabel, VerdictLabel
from app.pipeline.media_match import ArchiveIndex, Embed

Fetch = Callable[[str, Path], Downloaded]
REFUTED = (VerdictLabel.FALSE, VerdictLabel.MISLEADING)


@dataclass(frozen=True)
class Verdicted:
    """What a lesson needs from its published case."""

    case_id: str
    label: VerdictLabel
    rationale_en: str
    reported_on: date
    media: list[Path]
    page_url: str  # the post's link, or the public report page
    original_url: str | None


def teach(lesson: Verdicted, index: ArchiveIndex, embed: Embed, fetch: Fetch) -> list[str]:
    """Archive what this verdict teaches; returns the archive ids added."""
    # A corrected verdict replaces what the case taught before, label and wording both.
    archive.forget(f"case-{lesson.case_id}-", index)
    added: list[str] = []
    if lesson.original_url and lesson.label in REFUTED:
        added += _keep_original(lesson, lesson.original_url, index, embed, fetch)

    if lesson.label is VerdictLabel.TRUE:
        # The report date bounds the footage date from above, as an upload date does.
        label, when = ArchiveLabel.VERIFIED_GENUINE, lesson.reported_on
        # The checker's rationale names the event; the next case's verdict reads it.
        context = f"Verified genuine on Hamsa: {lesson.rationale_en[:200]}"
    elif lesson.label in REFUTED:
        label, when = ArchiveLabel.PRIOR, None
        context = f"Debunked on Hamsa as {lesson.label}: {lesson.rationale_en[:200]}"
    else:
        return added  # an unverifiable post teaches nothing about its footage

    eval_posts = archive.eval_media_hashes()
    for i, path in enumerate(lesson.media):
        # A test case made from an eval post would make that post match itself.
        if hashlib.sha256(path.read_bytes()).hexdigest() in eval_posts:
            continue
        archive_id = f"case-{lesson.case_id}-{i}"
        archive.keep_keyframes(
            archive_id, frames_of(path), label, context, when, lesson.page_url, index, embed
        )
        added.append(archive_id)
    return added


def _keep_original(
    lesson: Verdicted, url: str, index: ArchiveIndex, embed: Embed, fetch: Fetch
) -> list[str]:
    known = {u.rstrip("/") for u in archive.eval_post_urls()}
    known |= {str(r.source_url).rstrip("/") for r in archive.manifest_rows()}
    if url.rstrip("/") in known:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        original = fetch(url, Path(tmp))
        if not original.files:
            return []
        slug = re.sub(r"[^a-z0-9]+", "-", url.lower().split("//")[-1]).strip("-")
        archive_id = f"original-{slug}"[:80].rstrip("-")
        title = original.title or url
        uploaded = f", uploaded {original.uploaded}" if original.uploaded else ""
        context = f"Original found by a checker: {title}{uploaded}"
        archive.keep_keyframes(
            archive_id,
            frames_of(original.files[0]),
            ArchiveLabel.PRIOR,
            context,
            original.uploaded,
            url,
            index,
            embed,
        )
    return [archive_id]
