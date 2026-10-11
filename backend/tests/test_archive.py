import csv
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app import archive
from app.eval.dataset import EvalItem
from app.pipeline.contracts import ArchiveLabel

MANIFEST_HEADER = list(archive.ManifestRow.model_fields)


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    archive_dir, eval_dir = tmp_path / "archive", tmp_path / "eval"
    archive_dir.mkdir()
    eval_dir.mkdir()
    monkeypatch.setattr(archive, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(archive, "EVAL_DIR", eval_dir)
    write(archive_dir / "manifest.csv", MANIFEST_HEADER, [])
    write(eval_dir / "items.csv", list(EvalItem.model_fields), [])
    return archive_dir, eval_dir


def write(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows([{k: row.get(k, "") for k in header} for row in rows])


GENUINE = {
    "archive_id": "ndrrma-melamchi-0827",
    "media_file": "melamchi.mp4",
    "label": "verified_genuine",
    "original_context": "NDRRMA footage of Melamchi, 2026-08-27",
    "original_date": "2026-08-27",
    "source_url": "https://bipad.gov.np/example",
}

RECYCLED = {
    "id": "h001",
    "kind": "video",
    "platform": "tiktok",
    "language": "ne",
    "claim_text": "रसुवामा हिमताल फुट्यो",
    "post_url": "https://www.tiktok.com/@x/video/1",
    "media_file": "h001.mp4",
    "verdict": "false",
    "tactic": "recycled",
    "original_source_url": "https://www.youtube.com/watch?v=alaska",
    "original_context": "Columbia Glacier, Alaska",
    "original_media_file": "h001_orig.mp4",
    "fact_check_url": "https://nepalfactcheck.org/2026/08/example",
}


def test_collects_manifest_rows_and_recycled_eval_originals(dirs: tuple[Path, Path]) -> None:
    archive_dir, eval_dir = dirs
    write(archive_dir / "manifest.csv", MANIFEST_HEADER, [GENUINE])
    write(eval_dir / "items.csv", list(EvalItem.model_fields), [RECYCLED])

    entries = archive.collect_entries()

    assert [(e.archive_id, e.label, p.name) for e, p in entries] == [
        ("ndrrma-melamchi-0827", ArchiveLabel.VERIFIED_GENUINE, "melamchi.mp4"),
        ("eval-h001", ArchiveLabel.PRIOR, "h001_orig.mp4"),
    ]
    assert entries[1][0].original_context == "Columbia Glacier, Alaska"


def test_eval_posts_themselves_never_enter_the_archive(dirs: tuple[Path, Path]) -> None:
    _, eval_dir = dirs
    without_original = RECYCLED | {"original_media_file": ""}
    genuine_post = {
        **RECYCLED,
        "id": "h002",
        "verdict": "true",
        "tactic": "none",
        "original_media_file": "",
        "evidence_urls": "https://kathmandupost.com/a",
    }
    write(eval_dir / "items.csv", list(EvalItem.model_fields), [without_original, genuine_post])

    assert archive.collect_entries() == []


def test_duplicate_archive_ids_are_rejected(dirs: tuple[Path, Path]) -> None:
    archive_dir, _ = dirs
    write(archive_dir / "manifest.csv", MANIFEST_HEADER, [GENUINE, GENUINE])
    with pytest.raises(ValueError, match="duplicate archive ids: ndrrma-melamchi-0827"):
        archive.collect_entries()


def test_manifest_rows_are_validated(dirs: tuple[Path, Path]) -> None:
    archive_dir, _ = dirs
    write(archive_dir / "manifest.csv", MANIFEST_HEADER, [GENUINE | {"label": "maybe"}])
    with pytest.raises(ValidationError):
        archive.collect_entries()


def fake_ytdlp(info: dict[str, Any]) -> Any:
    def run(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        folder = Path(command[command.index("-o") + 1]).parent
        (folder / "clip.mp4").write_bytes(b"video")
        (folder / "clip.info.json").write_text(json.dumps(info))
        return subprocess.CompletedProcess(command, 0, "", "")

    return run


YOUTUBE_INFO = {
    "extractor_key": "Youtube",
    "id": "E8-pRam3KPo",
    "title": "Massive landslide plunges into Nepal's Kali Gandaki River",
    "upload_date": "20260928",
    "webpage_url": "https://www.youtube.com/watch?v=E8-pRam3KPo",
}


def test_add_downloads_the_clip_and_appends_a_manifest_row(
    dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    archive_dir, _ = dirs
    monkeypatch.setattr(archive.subprocess, "run", fake_ytdlp(YOUTUBE_INFO))

    row = archive.add(
        "https://youtu.be/E8-pRam3KPo", ArchiveLabel.VERIFIED_GENUINE, "Lete landslide, Mustang"
    )

    assert row.archive_id == "youtube-e8-pram3kpo"
    assert row.original_date == date(2026, 9, 28)
    assert (archive_dir / "media" / "youtube-e8-pram3kpo.mp4").read_bytes() == b"video"
    [(entry, path)] = archive.collect_entries()
    assert entry.original_context.startswith("Lete landslide, Mustang: Massive landslide")
    assert path.name == "youtube-e8-pram3kpo.mp4"


def test_add_refuses_eval_posts_even_behind_a_short_link(
    dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, eval_dir = dirs
    post = RECYCLED | {"post_url": "https://www.youtube.com/watch?v=E8-pRam3KPo"}
    write(eval_dir / "items.csv", list(EvalItem.model_fields), [post])
    monkeypatch.setattr(archive.subprocess, "run", fake_ytdlp(YOUTUBE_INFO))

    with pytest.raises(ValueError, match="is an eval post"):
        archive.add("https://youtu.be/E8-pRam3KPo", ArchiveLabel.VERIFIED_GENUINE, "Lete")


def test_add_refuses_draft_eval_posts(
    dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, eval_dir = dirs
    draft = RECYCLED | {"post_url": "https://www.youtube.com/watch?v=E8-pRam3KPo"}
    write(eval_dir / "drafts.csv", list(EvalItem.model_fields), [draft])
    monkeypatch.setattr(archive.subprocess, "run", fake_ytdlp(YOUTUBE_INFO))

    with pytest.raises(ValueError, match="is an eval post"):
        archive.add(YOUTUBE_INFO["webpage_url"], ArchiveLabel.VERIFIED_GENUINE, "Lete")


def test_add_refuses_a_clip_already_archived(
    dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(archive.subprocess, "run", fake_ytdlp(YOUTUBE_INFO))
    archive.add(YOUTUBE_INFO["webpage_url"], ArchiveLabel.VERIFIED_GENUINE, "Lete")
    with pytest.raises(ValueError, match="already in the archive"):
        archive.add(YOUTUBE_INFO["webpage_url"], ArchiveLabel.VERIFIED_GENUINE, "Lete")


def test_eval_overlaps_reports_only_strong_matches() -> None:
    same = [1.0] * 64
    near = [-1.0] * 10 + [1.0] * 54  # 10 bits differ
    far = [-1.0] * 30 + [1.0] * 34
    found = archive.eval_overlaps({"clip": [same]}, {"h001": [near], "h002": [far]})
    assert found == ["clip matches eval post h001 (pHash 10)"]
