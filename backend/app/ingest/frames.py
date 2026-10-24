"""Turn an image or video into a few representative frames (architecture 3.1)."""

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageOps

MAX_FRAMES = 6
MAX_SHORT_SIDE = 720
SAMPLES_PER_SECOND = 2
MAX_SAMPLES = 600  # five minutes of video at 2 samples per second
# Mean absolute difference (0-255) between consecutive 32x32 grayscale samples that
# counts as a scene change. Hard cuts in news clips score 30+; camera shake scores < 10.
SCENE_CHANGE = 18.0
# Grayscale standard deviation (0-255) of a 32x32 sample below which it is blank. A black
# frame hashes the same in every clip: one at the end of a real flood video "matched" three
# 2015 earthquake clips at pHash distance 0 (case 6545c12251cd, 2026-10-21).
BLANK_STD = 8.0


IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp"})
VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv", ".m4v"})


@dataclass(frozen=True)
class Frame:
    index: int
    timestamp_s: float
    image: Image.Image


def frames_of(path: Path) -> list[Frame]:
    if path.is_dir():  # keyframes kept from footage found online (ADR 0011)
        images = sorted(p for p in path.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
        return [Frame(i, 0.0, frames_from_image(p)[0].image) for i, p in enumerate(images)]
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return frames_from_image(path)
    if suffix in VIDEO_SUFFIXES:
        return keyframes_from_video(path)
    raise ValueError(f"unsupported media type {suffix}")


def frames_from_image(path: Path) -> list[Frame]:
    with Image.open(path) as opened:
        # exif_transpose applies the camera rotation before EXIF is dropped by convert.
        image = _fit(ImageOps.exif_transpose(opened).convert("RGB"))
    return [Frame(index=0, timestamp_s=0.0, image=image)]


def keyframes_from_video(path: Path, max_frames: int = MAX_FRAMES) -> list[Frame]:
    """First frame, then the strongest scene changes, padded with evenly spaced samples.

    Blank samples are never chosen, unless the whole video is blank.
    """
    samples = _sample(path)
    if not samples:
        raise ValueError(f"no decodable video frames in {path.name}")

    thumbs = [thumb for _, thumb, _ in samples]
    shown = [i for i, thumb in enumerate(thumbs) if thumb.std() >= BLANK_STD]
    shown = shown or list(range(len(samples)))
    change = [0.0] + [float(np.abs(b - a).mean()) for a, b in pairwise(thumbs)]
    cuts = sorted(
        (i for i in shown[1:] if change[i] >= SCENE_CHANGE),
        key=lambda i: change[i],
        reverse=True,
    )

    chosen = [shown[0], *cuts[: max_frames - 1]]
    if len(chosen) < max_frames:
        spaced = np.linspace(0, len(shown) - 1, num=min(max_frames, len(shown)), dtype=int)
        padding = [shown[int(i)] for i in spaced if shown[int(i)] not in chosen]
        chosen += padding[: max_frames - len(chosen)]

    return [
        Frame(index=n, timestamp_s=samples[i][0], image=samples[i][2])
        for n, i in enumerate(sorted(chosen))
    ]


def _sample(path: Path) -> list[tuple[float, np.ndarray, Image.Image]]:
    """Each sample's time, 32x32 thumbnail and frame fitted to 720p.

    Full-size frames are never kept: 600 of them from a 4K upload would need ~10 GB.
    shortcut: still holds up to 600 fitted frames (~1.6 GB at 720p); decode twice if that bites.
    """
    samples: list[tuple[float, np.ndarray, Image.Image]] = []
    next_time = 0.0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            if frame.pts is None or frame.time < next_time:
                continue
            image = Image.fromarray(frame.to_ndarray(format="rgb24"))
            samples.append((round(frame.time, 2), _thumbnail(image), _fit(image)))
            next_time = frame.time + 1 / SAMPLES_PER_SECOND
            if len(samples) >= MAX_SAMPLES:
                break
    return samples


def _thumbnail(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("L").resize((32, 32)), dtype=np.float32)


def _fit(image: Image.Image) -> Image.Image:
    short = min(image.size)
    if short <= MAX_SHORT_SIDE:
        return image
    scale = MAX_SHORT_SIDE / short
    return image.resize((round(image.width * scale), round(image.height * scale)))
