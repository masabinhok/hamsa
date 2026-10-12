from collections.abc import Callable, Sequence

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from qdrant_client import QdrantClient

from app.ingest.frames import Frame
from app.pipeline.contracts import ArchiveLabel
from app.pipeline.media_match import (
    SIGLIP_DIM,
    ArchiveEntry,
    ArchiveIndex,
    Embeddings,
    canonical,
    hamming,
    inliers,
    match_media,
    orb_features,
    phash_vector,
)
from tests.images import letterbox, photo, textured


def fake_embed(images: Sequence[Image.Image]) -> Embeddings:
    """Stand-in for SigLIP: a normalised 16x16 thumbnail, so similar images score close."""
    rows: list[NDArray[np.float32]] = []
    for image in images:
        thumb = np.asarray(image.convert("L").resize((16, 16)), dtype=np.float32).flatten()
        vector = np.zeros(SIGLIP_DIM, dtype=np.float32)
        vector[: thumb.size] = thumb - thumb.mean()
        rows.append(vector / np.linalg.norm(vector))
    return np.stack(rows)


ORIGINAL = ArchiveEntry(
    archive_id="kullu-2023",
    label=ArchiveLabel.PRIOR,
    original_context="2023 Himachal Pradesh floods, Kullu",
    original_date=None,
    source_url="https://www.youtube.com/watch?v=abc",
)


@pytest.fixture
def index() -> ArchiveIndex:
    archive = ArchiveIndex(QdrantClient(":memory:"))
    archive.recreate()
    archive.add(ORIGINAL, [Frame(0, 0.0, photo(7))], fake_embed)
    return archive


def frames(*images: Image.Image) -> list[Frame]:
    return [Frame(i, float(i), image) for i, image in enumerate(images)]


def test_hamming_counts_differing_bits() -> None:
    vector = phash_vector(photo(1))
    assert hamming(vector, vector) == 0
    assert hamming(vector, [-v for v in vector]) == 64


def test_canonical_strips_letterbox_bars() -> None:
    original = photo(1)
    assert canonical(letterbox(original)).size == original.size


def test_canonical_keeps_a_small_subject_on_plain_background() -> None:
    canvas = Image.new("RGB", (800, 800), "white")
    canvas.paste(photo(1, size=(200, 200)), (300, 300))
    assert canonical(canvas).size == (800, 800)


def test_reencoded_repost_matches_with_archive_context(index: ArchiveIndex) -> None:
    repost = photo(7).resize((320, 240))

    [hit] = match_media(frames(repost), index, fake_embed).hits

    assert hit.archive_id == "kullu-2023"
    assert hit.phash_distance is not None
    assert hit.phash_distance <= 2
    assert hit.archive_label is ArchiveLabel.PRIOR
    assert hit.original_context == "2023 Himachal Pradesh floods, Kullu"


@pytest.mark.parametrize("edit", [ImageOps.mirror, letterbox], ids=["mirror", "letterbox"])
def test_common_repost_edits_still_match_exactly(
    index: ArchiveIndex, edit: Callable[[Image.Image], Image.Image]
) -> None:
    repost = edit(photo(7))
    [hit] = match_media(frames(repost), index, fake_embed).hits
    assert hit.phash_distance == 0


def test_unrelated_image_produces_no_hit(index: ArchiveIndex) -> None:
    assert match_media(frames(photo(99)), index, fake_embed).hits == []


def test_one_hit_per_archive_item_from_the_best_frame(index: ArchiveIndex) -> None:
    result = match_media(frames(photo(99), photo(7)), index, fake_embed)
    [hit] = result.hits
    assert hit.frame_index == 1
    assert hit.phash_distance == 0


def test_no_frames_means_no_hits(index: ArchiveIndex) -> None:
    assert match_media([], index, fake_embed).hits == []


def tiktok_style(image: Image.Image) -> Image.Image:
    """Crop the middle, add a caption, and set it on blurred bars: what defeats pHash."""
    middle = image.crop((120, 40, 520, 440))
    ImageDraw.Draw(middle).rectangle((0, 0, middle.width, 40), fill="white")
    canvas = image.resize((720, 720)).filter(ImageFilter.GaussianBlur(25))
    canvas.paste(middle, ((720 - middle.width) // 2, (720 - middle.height) // 2))
    return canvas


def test_orb_finds_footage_inside_a_reframed_repost() -> None:
    original = orb_features(textured(3))
    repost = orb_features(tiktok_style(textured(3)))
    unrelated = orb_features(textured(4))
    assert original
    assert repost
    assert unrelated
    assert inliers(repost, original) >= 100
    assert inliers(unrelated, original) < 20


def test_reframed_repost_matches_through_the_archive_by_geometry() -> None:
    archive = ArchiveIndex(QdrantClient(":memory:"))
    archive.recreate()
    archive.add(ORIGINAL, [Frame(0, 0.0, textured(3))], fake_embed)

    [hit] = match_media(frames(tiktok_style(textured(3))), archive, fake_embed).hits

    assert hit.archive_id == "kullu-2023"
    assert hit.inliers is not None
    assert hit.inliers >= 100
