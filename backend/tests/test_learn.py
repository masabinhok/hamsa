import csv
import shutil
from datetime import date
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from app import archive
from app.eval.dataset import EvalItem
from app.ingest.download import Downloaded
from app.ingest.frames import Frame
from app.learn import Verdicted, teach
from app.pipeline.contracts import ArchiveLabel, VerdictLabel
from app.pipeline.media_match import ArchiveIndex, match_media
from app.router.route import is_strong_match
from tests.images import textured, write_video
from tests.test_media_match import fake_embed, tiktok_style


@pytest.fixture
def index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ArchiveIndex:
    archive_dir, eval_dir = tmp_path / "archive", tmp_path / "eval"
    (eval_dir / "media").mkdir(parents=True)
    archive_dir.mkdir()
    monkeypatch.setattr(archive, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(archive, "EVAL_DIR", eval_dir)
    for path, header in (
        (archive_dir / "manifest.csv", list(archive.ManifestRow.model_fields)),
        (eval_dir / "items.csv", list(EvalItem.model_fields)),
    ):
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=header).writeheader()
    store = ArchiveIndex(QdrantClient(":memory:"))
    store.recreate()
    return store


def lesson(tmp_path: Path, label: VerdictLabel, original_url: str | None = None) -> Verdicted:
    video = write_video(tmp_path / "post.mp4", [textured(3)], seconds_each=1.0)
    return Verdicted(
        case_id="c1",
        label=label,
        rationale_en="The footage is from Alaska.",
        reported_on=date(2026, 8, 27),
        media=[video],
        page_url="http://localhost:3000/check/c1",
        original_url=original_url,
    )


def never_fetch(url: str, folder: Path) -> Downloaded:
    raise AssertionError("no original to fetch")


def strong_hits(index: ArchiveIndex) -> list[str]:
    repost = [Frame(0, 0.0, tiktok_style(textured(3)))]
    return [h.archive_id for h in match_media(repost, index, fake_embed).hits if is_strong_match(h)]


def test_a_true_verdict_makes_its_footage_known_genuine(
    tmp_path: Path, index: ArchiveIndex
) -> None:
    assert teach(lesson(tmp_path, VerdictLabel.TRUE), index, fake_embed, never_fetch) == [
        "case-c1-0"
    ]
    [row] = archive.manifest_rows()
    assert (row.label, row.original_date) == (ArchiveLabel.VERIFIED_GENUINE, date(2026, 8, 27))
    assert row.original_context == "Verified genuine on Hamsa: The footage is from Alaska."
    assert strong_hits(index) == ["case-c1-0"]  # a later repost is recognised


def test_a_refuted_verdict_keeps_the_checkers_original_and_the_post(
    tmp_path: Path, index: ArchiveIndex
) -> None:
    def fetch(url: str, folder: Path) -> Downloaded:
        video = write_video(folder / "post.mp4", [textured(5)], seconds_each=1.0)
        return Downloaded([video], "caption", "Glacier calving, Alaska", date(2020, 1, 15))

    added = teach(
        lesson(tmp_path, VerdictLabel.FALSE, "https://youtu.be/alaska"), index, fake_embed, fetch
    )

    assert added == ["original-youtu-be-alaska", "case-c1-0"]
    original, post = archive.manifest_rows()
    assert (original.label, original.original_date) == (ArchiveLabel.PRIOR, date(2020, 1, 15))
    assert original.original_context.startswith("Original found by a checker: Glacier calving")
    assert post.label is ArchiveLabel.PRIOR
    assert post.original_context.startswith("Debunked on Hamsa as false")


def test_an_eval_post_never_teaches_the_archive(tmp_path: Path, index: ArchiveIndex) -> None:
    taught = lesson(tmp_path, VerdictLabel.TRUE)
    shutil.copy(taught.media[0], archive.EVAL_DIR / "media" / "h001.mp4")
    assert teach(taught, index, fake_embed, never_fetch) == []
    assert archive.manifest_rows() == []


def test_an_unverifiable_verdict_teaches_nothing(tmp_path: Path, index: ArchiveIndex) -> None:
    assert teach(lesson(tmp_path, VerdictLabel.UNVERIFIABLE), index, fake_embed, never_fetch) == []
