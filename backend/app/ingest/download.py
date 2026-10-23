"""Download a post's media from its link with yt-dlp (ADR 0010), or its link preview.

Shared by the worker, for pasted links, and the archive collector.
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import httpx

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
# Platforms serve the caption and picture behind a link preview to their own crawler, even
# for posts yt-dlp cannot open: Facebook photo posts (404) and restricted reels.
PREVIEW_AGENT = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"


@dataclass(frozen=True)
class Downloaded:
    files: list[Path]
    # The post's own words: for a pasted link this is the claim to check.
    caption: str | None
    title: str | None = None
    uploaded: date | None = None
    # The platform's own id ("Youtube:EmM79Xzvbg0"), the same however the link was shared.
    post_id: str | None = None


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
        except subprocess.CalledProcessError as error:
            if i < len(attempts) - 1:
                continue
            try:
                return preview(url, folder)
            except (httpx.HTTPError, ValueError):
                raise error from None
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
        post_id=f"{meta['extractor_key']}:{meta['id']}"
        if meta.get("extractor_key") and meta.get("id")
        else None,
    )


class _MetaTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        found = dict(attrs)
        key, content = found.get("property") or found.get("name"), found.get("content")
        if tag == "meta" and key and content:
            self.tags.setdefault(key, content)


def meta_tags(markup: str) -> dict[str, str]:
    """A page's <meta> properties (og:*, article:*), first value of each."""
    parser = _MetaTags()
    parser.feed(markup)
    return parser.tags


def preview(url: str, folder: Path, http: httpx.Client | None = None) -> Downloaded:
    """The caption and picture of a post's link preview. For a video this is one still, so
    a checker may still need the file. Raises when the page has neither."""
    http = http or httpx.Client(
        timeout=15, follow_redirects=True, headers={"User-Agent": PREVIEW_AGENT}
    )
    page = http.get(url)
    page.raise_for_status()
    tags = meta_tags(page.text)
    # A blocked or removed post serves the platform's own landing preview, typed "website"
    # (TikTok: its logo and "Watch, follow, and discover more trending content.").
    if tags.get("og:type") == "website":
        raise ValueError(f"no post preview at {url}, only the site's")
    caption = (tags.get("og:description") or "").strip() or None
    files: list[Path] = []
    if image_url := tags.get("og:image"):
        image = http.get(image_url)
        image.raise_for_status()
        (folder / "preview.img").write_bytes(image.content)  # the worker sniffs its type
        files.append(folder / "preview.img")
    if caption is None and not files:
        raise ValueError(f"no link preview at {url}")
    published = tags.get("article:published_time")
    return Downloaded(
        files=files,
        caption=caption,
        title=tags.get("og:title"),
        uploaded=datetime.fromisoformat(published).date() if published else None,
    )
