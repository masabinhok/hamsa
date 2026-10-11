"""Synthetic test media: structured enough for pHash, deterministic per seed."""

from pathlib import Path
from typing import Any

import av
import numpy as np
from PIL import Image, ImageFilter


def photo(seed: int, size: tuple[int, int] = (640, 480)) -> Image.Image:
    """Blurred colour noise: smooth blobs with real low-frequency structure, like a photo."""
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (12, 16, 3), dtype=np.uint8)
    return (
        Image.fromarray(small)
        .resize(size, Image.Resampling.BICUBIC)
        .filter(ImageFilter.GaussianBlur(4))
    )


def letterbox(image: Image.Image) -> Image.Image:
    canvas = Image.new("RGB", (image.width, image.width * 16 // 9), "black")
    canvas.paste(image, (0, (canvas.height - image.height) // 2))
    return canvas


def write_video(path: Path, scenes: list[Image.Image], seconds_each: float, fps: int = 10) -> Path:
    with av.open(str(path), "w") as opened:
        # PyAV's encoder API is only partly typed; keep it behind Any in this helper.
        container: Any = opened
        stream: Any = container.add_stream("libx264", rate=fps)
        stream.width, stream.height = scenes[0].size
        stream.pix_fmt = "yuv420p"
        for scene in scenes:
            for _ in range(int(seconds_each * fps)):
                frame = av.VideoFrame.from_ndarray(np.asarray(scene.convert("RGB")), format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path
