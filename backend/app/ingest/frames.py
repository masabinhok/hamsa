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


@dataclass(frozen=True)
class Frame:
    index: int
    timestamp_s: float
    image: Image.Image


def frames_from_image(path: Path) -> list[Frame]:
    with Image.open(path) as opened:
        # exif_transpose applies the camera rotation before EXIF is dropped by convert.
        image = _fit(ImageOps.exif_transpose(opened).convert("RGB"))
    return [Frame(index=0, timestamp_s=0.0, image=image)]


def keyframes_from_video(path: Path, max_frames: int = MAX_FRAMES) -> list[Frame]:
    """First frame, then the strongest scene changes, padded with evenly spaced samples."""
    samples = _sample(path)
    if not samples:
        raise ValueError(f"no decodable video frames in {path.name}")

    thumbs = [_thumbnail(image) for _, image in samples]
    change = [0.0] + [float(np.abs(b - a).mean()) for a, b in pairwise(thumbs)]
    cuts = sorted(
        (i for i in range(1, len(samples)) if change[i] >= SCENE_CHANGE),
        key=lambda i: change[i],
        reverse=True,
    )

    chosen = [0, *cuts[: max_frames - 1]]
    if len(chosen) < max_frames:
        spaced = np.linspace(0, len(samples) - 1, num=min(max_frames, len(samples)), dtype=int)
        chosen += [int(i) for i in spaced if int(i) not in chosen][: max_frames - len(chosen)]

    return [
        Frame(index=n, timestamp_s=samples[i][0], image=_fit(samples[i][1]))
        for n, i in enumerate(sorted(chosen))
    ]


def _sample(path: Path) -> list[tuple[float, Image.Image]]:
    samples: list[tuple[float, Image.Image]] = []
    next_time = 0.0
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for frame in container.decode(stream):
            if frame.pts is None or frame.time < next_time:
                continue
            image = Image.fromarray(frame.to_ndarray(format="rgb24"))
            samples.append((round(frame.time, 2), image))
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
