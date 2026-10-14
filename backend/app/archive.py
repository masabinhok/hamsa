"""The media archive, from backend/:

- `uv run python -m app.archive` builds it in Qdrant.
- `uv run python -m app.archive add <url> --label verified_genuine --context "..."` downloads
  one clip with yt-dlp and appends it to the manifest; checkers use this on the day of a disaster.

Sources:
- data/archive/manifest.csv: footage collected for the archive (prior or verified genuine).
- data/eval/items.csv: the original behind each recycled eval item, as prior footage.
  Only originals are added, never the posts themselves, so eval matching stays honest.
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl
from qdrant_client import QdrantClient

from app.config import REPO_ROOT, get_settings
from app.eval.dataset import Tactic, load_items
from app.ingest.download import YTDLP as DOWNLOAD_COMMAND
from app.ingest.frames import frames_of
from app.pipeline.contracts import ArchiveLabel
from app.pipeline.media_match import (
    ArchiveEntry,
    ArchiveIndex,
    SiglipEmbedder,
    canonical,
    hamming,
    phash_vector,
)
from app.router.route import DEFAULT_THRESHOLDS

ARCHIVE_DIR = REPO_ROOT / "data" / "archive"
EVAL_DIR = REPO_ROOT / "data" / "eval"

# The archive also reads the title and upload date from yt-dlp's info file.
YTDLP = (*DOWNLOAD_COMMAND, "--write-info-json")


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
                media=f"archive/media/{row.media_file}",
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
            media=f"eval/media/{original}",
        )
        entries.append((entry, EVAL_DIR / "media" / original))

    ids = [entry.archive_id for entry, _ in entries]
    if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
        raise ValueError(f"duplicate archive ids: {', '.join(duplicates)}")
    return entries


def _same_url(a: str, b: str) -> bool:
    return a.rstrip("/") == b.rstrip("/")


def add(
    url: str,
    label: ArchiveLabel,
    context: str,
    original_date: date | None = None,
    browser: str | None = None,
) -> ManifestRow:
    """Download one clip and append it to the manifest. The upload date stands in for the
    footage date unless one is given; it is an upper bound, since outlets reuse footage."""
    eval_posts = [str(i.post_url) for i in load_items(EVAL_DIR / "items.csv") if i.post_url]
    drafts = EVAL_DIR / "drafts.csv"  # the owner's unverified rows, gitignored
    if drafts.is_file():
        with drafts.open(newline="", encoding="utf-8") as handle:
            eval_posts += [r["post_url"] for r in csv.DictReader(handle) if r.get("post_url")]
    manifest = ARCHIVE_DIR / "manifest.csv"
    with manifest.open(newline="", encoding="utf-8") as handle:
        rows = [ManifestRow.model_validate(raw) for raw in csv.DictReader(handle)]

    def refuse_known(candidate: str) -> None:
        # A post that matches itself proves nothing (docs/data-collection.md).
        if any(_same_url(candidate, post) for post in eval_posts):
            raise ValueError(f"{candidate} is an eval post; it must not enter the archive")
        if any(_same_url(candidate, str(row.source_url)) for row in rows):
            raise ValueError(f"{candidate} is already in the archive")

    refuse_known(url)
    with tempfile.TemporaryDirectory() as tmp:
        command = [*YTDLP, "-o", f"{tmp}/clip.%(ext)s"]
        if browser:
            command += ["--cookies-from-browser", browser]
        # "--" keeps a url starting with "-" from being read as a yt-dlp option.
        subprocess.run([*command, "--", url], check=True, capture_output=True, text=True)  # noqa: S603
        info = json.loads((Path(tmp) / "clip.info.json").read_text(encoding="utf-8"))
        clip = next(p for p in Path(tmp).iterdir() if not p.name.endswith(".json"))

        source_url = info.get("webpage_url") or url
        if not _same_url(source_url, url):
            refuse_known(source_url)
        archive_id = re.sub(r"[^a-z0-9]+", "-", f"{info['extractor_key']}-{info['id']}".lower())
        uploaded = info.get("upload_date")
        row = ManifestRow(
            archive_id=archive_id.strip("-"),
            media_file=f"{archive_id.strip('-')}{clip.suffix}",
            label=label,
            original_context=f"{context}: {info.get('title') or 'untitled'}",
            original_date=original_date
            or (datetime.strptime(uploaded, "%Y%m%d").date() if uploaded else None),
            source_url=HttpUrl(source_url),
        )
        if any(r.archive_id == row.archive_id for r in rows):
            raise ValueError(f"archive id {row.archive_id} is already in the archive")
        (ARCHIVE_DIR / "media").mkdir(exist_ok=True)
        shutil.move(clip, ARCHIVE_DIR / "media" / row.media_file)

    with manifest.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ManifestRow.model_fields))
        writer.writerow(row.model_dump(mode="json"))
    return row


def eval_overlaps(
    archive_hashes: dict[str, list[list[float]]], eval_hashes: dict[str, list[list[float]]]
) -> list[str]:
    """Manifest clips that strongly match an eval post. Not an error: genuine footage of
    an event can be archived before its reposts arrive. The owner decides per pair."""
    limit = DEFAULT_THRESHOLDS.phash_max_distance
    found: list[str] = []
    for archive_id, hashes in archive_hashes.items():
        for item_id, post_hashes in eval_hashes.items():
            distance = min(hamming(a, b) for a in hashes for b in post_hashes)
            if distance <= limit:
                found.append(f"{archive_id} matches eval post {item_id} (pHash {distance})")
    return found


def _hashes(path: Path) -> list[list[float]]:
    return [phash_vector(canonical(frame.image)) for frame in frames_of(path)]


def build() -> int:
    entries = collect_entries()
    index = ArchiveIndex(QdrantClient(url=str(get_settings().qdrant_url)))
    index.recreate()
    embed = SiglipEmbedder()

    indexed = 0
    problems: list[str] = []
    manifest_hashes: dict[str, list[list[float]]] = {}
    for entry, path in entries:
        if not path.is_file():
            problems.append(f"{entry.archive_id}: missing {path.relative_to(REPO_ROOT)}")
            continue
        try:
            frames = frames_of(path)
            indexed += index.add(entry, frames, embed)
        except (ValueError, OSError) as error:
            problems.append(f"{entry.archive_id}: {error}")
            continue
        if not entry.archive_id.startswith("eval-"):
            manifest_hashes[entry.archive_id] = [phash_vector(canonical(f.image)) for f in frames]

    eval_hashes = {
        item.id: _hashes(EVAL_DIR / "media" / item.media_file)
        for item in load_items(EVAL_DIR / "items.csv")
        if item.media_file and (EVAL_DIR / "media" / item.media_file).is_file()
    }
    print(f"archive: {len(entries) - len(problems)} items, {indexed} frames indexed")
    for overlap in eval_overlaps(manifest_hashes, eval_hashes):
        print(f"  check: {overlap}", file=sys.stderr)
    for problem in problems:
        print(f"  skipped {problem}", file=sys.stderr)
    return 1 if problems else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.archive")
    commands = parser.add_subparsers(dest="command")
    adding = commands.add_parser("add", help="download one clip into the manifest")
    adding.add_argument("url")
    adding.add_argument("--label", type=ArchiveLabel, required=True)
    adding.add_argument("--context", required=True, help="event, place and date, in words")
    adding.add_argument("--date", type=date.fromisoformat, help="footage date, if not upload")
    adding.add_argument("--browser", help="browser to take login cookies from, e.g. firefox")
    args = parser.parse_args(argv)
    if args.command != "add":
        return build()
    try:
        row = add(args.url, args.label, args.context, args.date, args.browser)
    except (ValueError, subprocess.CalledProcessError) as error:
        detail = getattr(error, "stderr", None) or str(error)
        print(f"not added: {detail.strip().splitlines()[-1]}", file=sys.stderr)
        return 1
    print(f"added {row.archive_id}: {row.original_context} ({row.original_date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
