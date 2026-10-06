import csv
from pathlib import Path

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
