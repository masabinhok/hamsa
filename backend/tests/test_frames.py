from pathlib import Path

import pytest
from PIL import Image

from app.ingest.frames import MAX_SHORT_SIDE, frames_from_image, frames_of, keyframes_from_video
from tests.images import photo, write_video


def test_image_is_rotated_by_exif_downscaled_and_rgb(tmp_path: Path) -> None:
    path = tmp_path / "phone.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 degrees clockwise
    photo(1, size=(2000, 1500)).convert("RGB").save(path, exif=exif)

    [frame] = frames_from_image(path)

    assert frame.image.mode == "RGB"
    assert frame.image.size == (MAX_SHORT_SIDE, 960)  # portrait after rotation
    assert frame.image.getexif().get(0x0112) is None


def test_small_image_is_not_upscaled(tmp_path: Path) -> None:
    path = tmp_path / "small.png"
    photo(2, size=(320, 240)).save(path)
    assert frames_from_image(path)[0].image.size == (320, 240)


def test_video_keyframes_land_on_scene_cuts(tmp_path: Path) -> None:
    video = write_video(tmp_path / "cuts.mp4", [photo(1), photo(2), photo(3)], seconds_each=2)

    frames = keyframes_from_video(video, max_frames=3)

    assert [f.timestamp_s for f in frames] == [0.0, 2.0, 4.0]
    assert [f.index for f in frames] == [0, 1, 2]


def test_static_video_is_padded_with_evenly_spaced_frames(tmp_path: Path) -> None:
    video = write_video(tmp_path / "static.mp4", [photo(1)], seconds_each=5)

    frames = keyframes_from_video(video, max_frames=4)

    assert len(frames) == 4
    assert frames[0].timestamp_s == 0.0
    assert frames[-1].timestamp_s >= 4.0


def test_undecodable_video_raises(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.mp4"
    bogus.write_bytes(b"not a video")
    with pytest.raises(Exception):  # noqa: B017, PT011 - PyAV raises its own error types
        keyframes_from_video(bogus)


def test_media_type_is_chosen_by_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"unsupported media type \.gif"):
        frames_of(tmp_path / "clip.gif")
