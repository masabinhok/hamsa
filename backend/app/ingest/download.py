"""Download a post's media from its link with yt-dlp (ADR 0010).

Shared by the worker, for pasted links, and the archive collector.
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Keyframes are capped at 6 per video, so footage past five minutes adds nothing.
YTDLP = (
    "yt-dlp",
    "--no-playlist",
    "--no-warnings",
    "-f",
    "bv*[height<=720]+ba/b",
    "--merge-output-format",
    "mp4",
    "--download-sections",
    "*0-300",
    "--max-filesize",
    "100M",
)
TIMEOUT_S = 300


@dataclass(frozen=True)
class Downloaded:
    files: list[Path]
    # The post's own words: for a pasted link this is the claim to check.
    caption: str | None
    title: str | None = None
    uploaded: date | None = None


def download(url: str, folder: Path, browser: str | None = None) -> Downloaded:
    """The media files and caption behind `url`, saved in `folder`. Raises on any failure.

    `browser` lends yt-dlp that browser's login (e.g. "firefox"); Facebook and TikTok
    need one. Hamsa runs on the agency's machine, so this is the operator's own session.
    """
    command = [*YTDLP, "--write-info-json", "-o", f"{folder}/post.%(ext)s"]
    # Facebook and TikTok need the login, but YouTube refuses requests that carry browser
    # cookies ("the page needs to be reloaded"), so a failed try is repeated without.
    attempts = [[*command, "--cookies-from-browser", browser], command] if browser else [command]
    for i, attempt in enumerate(attempts):
        try:
            # "--" keeps a url starting with "-" from being read as a yt-dlp option.
            subprocess.run(  # noqa: S603
                [*attempt, "--", url], check=True, capture_output=True, text=True, timeout=TIMEOUT_S
            )
            break
        except subprocess.CalledProcessError:
            if i == len(attempts) - 1:
                raise
    info = folder / "post.info.json"
    meta: dict[str, Any] = json.loads(info.read_text(encoding="utf-8")) if info.is_file() else {}
    caption: str | None = (meta.get("description") or meta.get("title") or "").strip() or None
    day: str | None = meta.get("upload_date")
    files = sorted(p for p in folder.iterdir() if p.suffix != ".json" and p.is_file())
    return Downloaded(
        files=files,
        caption=caption,
        title=meta.get("title"),
        uploaded=datetime.strptime(day, "%Y%m%d").date() if day else None,
    )
