"""Media-match robustness check: `uv run python -m app.eval.media_robustness` from backend/.

Runs the real matching path (canonical, pHash, SigLIP, Qdrant, router rule) on Creative
Commons flood photos with the edits reposts typically apply, plus hard negatives: other
photos of the same river. This is how the starting media thresholds were chosen; the eval
set then tunes them on real posts. Photos are downloaded on first run (CC BY-SA 4.0,
Wikimedia Commons; see SOURCES for attribution).
"""

import io
import sys
import urllib.request
from collections.abc import Callable
from datetime import date

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from qdrant_client import QdrantClient

from app.config import REPO_ROOT
from app.ingest.frames import Frame
from app.pipeline.contracts import ArchiveLabel
from app.pipeline.media_match import ArchiveEntry, ArchiveIndex, SiglipEmbedder, match_media
from app.router.route import is_strong_match

PHOTO_DIR = REPO_ROOT / "data" / "eval" / "robustness"
COMMONS = "https://upload.wikimedia.org/wikipedia/commons/thumb"
# (file name, Wikimedia Commons file page, thumbnail URL). All CC BY-SA 4.0.
SOURCES = [
    (
        "bagmati.jpg",
        "https://commons.wikimedia.org/wiki/File:Flood_in_River_Bagmati.jpg",
        f"{COMMONS}/c/ce/Flood_in_River_Bagmati.jpg/1280px-Flood_in_River_Bagmati.jpg",
    ),
    (
        "rato-2013.jpg",
        "https://commons.wikimedia.org/wiki/File:Enchente_do_r%C3%ADo_Rato_20I2013.JPG",
        f"{COMMONS}/1/18/Enchente_do_r%C3%ADo_Rato_20I2013.JPG/1280px-Enchente_do_r%C3%ADo_Rato_20I2013.JPG",
    ),
    (
        "rato-2016-a.jpg",
        "https://commons.wikimedia.org/wiki/File:R%C3%ADo_Rato_6IV2016_01.JPG",
        f"{COMMONS}/c/cc/R%C3%ADo_Rato_6IV2016_01.JPG/1280px-R%C3%ADo_Rato_6IV2016_01.JPG",
    ),
    (
        "rato-2016-b.jpg",
        "https://commons.wikimedia.org/wiki/File:R%C3%ADo_Rato_6IV2016_02.JPG",
        f"{COMMONS}/8/8c/R%C3%ADo_Rato_6IV2016_02.JPG/1280px-R%C3%ADo_Rato_6IV2016_02.JPG",
    ),
    (
        "rato-2016-bridge.jpg",
        "https://commons.wikimedia.org/wiki/File:Ponte_do_tren_sobre_o_r%C3%ADo_Rato_6IV2016_02.JPG",
        f"{COMMONS}/d/d5/Ponte_do_tren_sobre_o_r%C3%ADo_Rato_6IV2016_02.JPG/1280px-Ponte_do_tren_sobre_o_r%C3%ADo_Rato_6IV2016_02.JPG",
    ),
]
USER_AGENT = "hamsa-eval/0.1 (https://github.com/masabinhok/hamsa)"

Edit = Callable[[Image.Image], Image.Image]


def _jpeg(image: Image.Image, quality: int) -> Image.Image:
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality)
    return Image.open(buffer).convert("RGB")


def _crop(image: Image.Image, keep: float) -> Image.Image:
    dx, dy = int(image.width * (1 - keep) / 2), int(image.height * (1 - keep) / 2)
    return image.crop((dx, dy, image.width - dx, image.height - dy))


def _caption(image: Image.Image) -> Image.Image:
    out = image.copy()
    draw = ImageDraw.Draw(out)
    top = int(out.height * 0.82)
    draw.rectangle((0, top, out.width, out.height), fill=(200, 0, 0))
    draw.text((20, top + 30), "BREAKING: MELAMCHI SWEPT AWAY", fill="white")
    return out


def _letterbox(image: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (image.width, image.width * 16 // 9), "black")
    canvas.paste(image, (0, (canvas.height - image.height) // 2))
    return canvas


def _letterbox_blurred(image: Image.Image) -> Image.Image:
    height = image.width * 16 // 9
    fill = image.resize((height * image.width // image.height, height))
    left = (fill.width - image.width) // 2
    canvas = fill.filter(ImageFilter.GaussianBlur(25)).crop((left, 0, left + image.width, height))
    canvas.paste(image, (0, (height - image.height) // 2))
    return canvas


def _screenshot(image: Image.Image) -> Image.Image:
    small = image.resize((image.width // 2, image.height // 2))
    canvas = Image.new("RGB", (small.width, small.height + 120), (245, 245, 245))
    canvas.paste(small, (0, 60))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 10), "9:41  Ncell 4G  87%", fill="black")
    draw.text((10, canvas.height - 40), "12k likes  Share  Comment", fill="black")
    return _jpeg(ImageOps.autocontrast(canvas), 70)


EDITS: dict[str, Edit] = {
    "jpeg quality 30": lambda image: _jpeg(image, 30),
    "resized to 1/3": lambda image: image.resize((image.width // 3, image.height // 3)),
    "cropped to 90%": lambda image: _crop(image, 0.9),
    "cropped to 70%": lambda image: _crop(image, 0.7),
    "mirrored": ImageOps.mirror,
    "caption banner": _caption,
    "mirrored + caption": lambda image: _caption(ImageOps.mirror(image)),
    "letterbox, black bars": _letterbox,
    "letterbox, blurred bars": _letterbox_blurred,
    "phone screenshot": _screenshot,
}


def _download() -> list[Image.Image]:
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    photos: list[Image.Image] = []
    for name, _, url in SOURCES:
        path = PHOTO_DIR / name
        if not path.is_file():
            # Fixed https URLs from SOURCES, never user input.
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                path.write_bytes(response.read())
        photos.append(Image.open(path).convert("RGB"))
    return photos


def _entry(name: str) -> ArchiveEntry:
    return ArchiveEntry(
        archive_id=name.removesuffix(".jpg"),
        label=ArchiveLabel.PRIOR,
        original_context=f"robustness photo {name}",
        original_date=date(2016, 1, 1),
        source_url="https://commons.wikimedia.org/",
    )


def main() -> int:
    photos = _download()
    names = [name for name, _, _ in SOURCES]
    embed = SiglipEmbedder()

    def index_of(keep: list[int]) -> ArchiveIndex:
        index = ArchiveIndex(QdrantClient(":memory:"))
        index.recreate()
        for i in keep:
            index.add(_entry(names[i]), [Frame(0, 0.0, photos[i])], embed)
        return index

    full = index_of(list(range(len(photos))))
    anchors = [0, 1]
    print("Edited reposts (should match their original)")
    print(f"  {'edit':26}{'anchor':22}{'phash':>6}{'cosine':>8}  result")
    matched = total = 0
    for edit_name, edit in EDITS.items():
        for a in anchors:
            hits = match_media([Frame(0, 0.0, edit(photos[a]))], full, embed).hits
            hit = next((h for h in hits if h.archive_id == _entry(names[a]).archive_id), None)
            ok = hit is not None and is_strong_match(hit)
            matched += ok
            total += 1
            phash = "-" if hit is None else str(hit.phash_distance)
            cosine = "-" if hit is None else f"{hit.cosine:.3f}"
            print(
                f"  {edit_name:26}{names[a]:22}{phash:>6}{cosine:>8}  {'match' if ok else 'MISS'}"
            )

    print("\nDifferent photos (each queried against an archive of the others)")
    false_positives = 0
    for q in range(len(photos)):
        others = index_of([i for i in range(len(photos)) if i != q])
        hits = match_media([Frame(0, 0.0, photos[q])], others, embed).hits
        strong = [h for h in hits if is_strong_match(h)]
        false_positives += bool(strong)
        closest = max(hits, key=lambda h: h.cosine or 0.0, default=None)
        detail = (
            "no candidate"
            if closest is None
            else f"closest {closest.archive_id}: phash {closest.phash_distance}, "
            f"cosine {closest.cosine:.3f}"
        )
        print(f"  {names[q]:22}{'FALSE MATCH' if strong else 'no match':13}{detail}")

    print(f"\nrecall on edits: {matched}/{total}; false matches: {false_positives}/{len(photos)}")
    return 1 if false_positives else 0


if __name__ == "__main__":
    sys.exit(main())
