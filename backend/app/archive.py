"""Build the media archive in Qdrant: `uv run python -m app.archive` from backend/.

Sources:
- data/archive/manifest.csv: footage collected for the archive (prior or verified genuine).
- data/eval/items.csv: the original behind each recycled eval item, as prior footage.
  Only originals are added, never the posts themselves, so eval matching stays honest.
"""

import csv
import sys
from datetime import date
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl
from qdrant_client import QdrantClient

from app.config import REPO_ROOT, get_settings
from app.eval.dataset import Tactic, load_items
from app.ingest.frames import frames_of
from app.pipeline.contracts import ArchiveLabel
from app.pipeline.media_match import ArchiveEntry, ArchiveIndex, SiglipEmbedder

ARCHIVE_DIR = REPO_ROOT / "data" / "archive"
EVAL_DIR = REPO_ROOT / "data" / "eval"


def _blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


class ManifestRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    archive_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]
    media_file: Annotated[str, Field(min_length=1)]
    label: ArchiveLabel
    original_context: Annotated[str, Field(min_length=1)]
    original_date: Annotated[date | None, BeforeValidator(_blank_to_none)] = None
    source_url: HttpUrl


def collect_entries() -> list[tuple[ArchiveEntry, Path]]:
    entries: list[tuple[ArchiveEntry, Path]] = []
    with (ARCHIVE_DIR / "manifest.csv").open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row = ManifestRow.model_validate(raw)
            entry = ArchiveEntry(
                archive_id=row.archive_id,
                label=row.label,
                original_context=row.original_context,
                original_date=row.original_date,
                source_url=str(row.source_url),
            )
            entries.append((entry, ARCHIVE_DIR / "media" / row.media_file))

    for item in load_items(EVAL_DIR / "items.csv"):
        original = item.original_media_file
        if item.tactic is not Tactic.RECYCLED or not original:
            continue
        if item.original_source_url is None or item.original_context is None:
            continue  # unreachable: load_items requires both for recycled items
        entry = ArchiveEntry(
            archive_id=f"eval-{item.id}",
            label=ArchiveLabel.PRIOR,
            original_context=item.original_context,
            original_date=None,
            source_url=str(item.original_source_url),
        )
        entries.append((entry, EVAL_DIR / "media" / original))

    ids = [entry.archive_id for entry, _ in entries]
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        raise ValueError(f"duplicate archive ids: {', '.join(duplicates)}")
    return entries


def main() -> int:
    entries = collect_entries()
    index = ArchiveIndex(QdrantClient(url=str(get_settings().qdrant_url)))
    index.recreate()
    embed = SiglipEmbedder()

    indexed = 0
    problems: list[str] = []
    for entry, path in entries:
        if not path.is_file():
            problems.append(f"{entry.archive_id}: missing {path.relative_to(REPO_ROOT)}")
            continue
        try:
            indexed += index.add(entry, frames_of(path), embed)
        except (ValueError, OSError) as error:
            problems.append(f"{entry.archive_id}: {error}")

    print(f"archive: {len(entries) - len(problems)} items, {indexed} frames indexed")
    for problem in problems:
        print(f"  skipped {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
