"""What the platform itself shows on a post (ADR 0017): X's Community Note and TikTok's
AI-generated label, read from public pages without a login or an API key."""

import json
import logging
import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import HttpUrl, ValidationError

from app.ingest.download import is_platform_url
from app.pipeline.contracts import COMMUNITY_NOTE, PLATFORM_AI_LABEL, Passage, SourceKind

TIMEOUT_S = 10
# shortcut: X's embed endpoint is undocumented; if it changes, cases simply get no note.
SYNDICATION = "https://cdn.syndication.twimg.com/tweet-result"
BROWSER = "Mozilla/5.0 (X11; Linux x86_64; rv:131.0) Gecko/20100101 Firefox/131.0"
X_STATUS = re.compile(r"/status(?:es)?/(\d+)")
TIKTOK_VIDEO = re.compile(r"/video/(\d+)")
AIGC = re.compile(r'"IsAigc":\s*(true|false)')
AIGC_DESCRIPTION = re.compile(r'"AIGCDescription":\s*"((?:[^"\\]|\\.)*)"')
log = logging.getLogger("hamsa.platform")


def on_post(url: str | None, http: httpx.Client | None = None) -> list[Passage]:
    """Passages for what X or TikTok shows on this post; none for other links or on any
    failure, since a missing note must never fail a case."""
    if not url or not is_platform_url(url):
        return []
    host = urlsplit(url).hostname or ""
    http = http or httpx.Client(timeout=TIMEOUT_S, headers={"User-Agent": BROWSER})
    try:
        if host == "x.com" or host.endswith((".x.com", "twitter.com")):
            return _community_note(url, http)
        if host.endswith("tiktok.com"):
            return _tiktok_label(url, http)
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError) as error:
        log.info("no platform signal for %s: %s", url, type(error).__name__)
    return []


def _community_note(url: str, http: httpx.Client) -> list[Passage]:
    found = X_STATUS.search(urlsplit(url).path)
    if not found:
        return []
    tweet_id = found.group(1)
    # Without a token X returns a reduced post with no note; any value works today (the embed
    # widget derives one from the id, which X does not check).
    params = {"id": tweet_id, "lang": "en", "token": "0"}
    response = http.get(SYNDICATION, params=params)
    response.raise_for_status()
    note: dict[str, Any] | None = response.json().get("birdwatch_pivot")
    if not note:
        return []
    subtitle: dict[str, Any] = note.get("subtitle") or {}
    entities: list[dict[str, Any]] = subtitle.get("entities") or []
    links = [_unshortened(str(e["ref"]["url"]["url"]), http) for e in entities]
    text = str(subtitle.get("text", "")).strip()
    if links:
        text = text.split("\n\n")[0] + "\n\nSources in the note: " + ", ".join(links)
    return [
        Passage(
            passage_id=f"note-{note.get('noteId') or tweet_id}",
            source=COMMUNITY_NOTE,
            source_kind=SourceKind.PLATFORM,
            url=HttpUrl(str(note.get("destinationUrl") or url)),
            title=note.get("title") or "Readers added context",
            text=text,
            score=1.0,
        )
    ]


def _unshortened(short: str, http: httpx.Client) -> str:
    # Only the redirect's address is read; the page it points to is never fetched.
    try:
        # t.co answers browsers with a page, other clients with a plain redirect.
        response = http.head(short, follow_redirects=False, headers={"User-Agent": "Hamsa"})
        return response.headers.get("location") or short
    except httpx.HTTPError:
        return short


def _tiktok_label(url: str, http: httpx.Client) -> list[Passage]:
    if not TIKTOK_VIDEO.search(urlsplit(url).path):
        return []
    response = http.get(url, follow_redirects=True)
    response.raise_for_status()
    page = response.text
    labelled = AIGC.search(page)
    if not labelled or labelled.group(1) != "true":
        return []
    described = AIGC_DESCRIPTION.search(page)
    detail = json.loads(f'"{described.group(1)}"').strip() if described else ""
    text = "TikTok labels this video as AI-generated." + (f" {detail}" if detail else "")
    video_id = TIKTOK_VIDEO.search(urlsplit(url).path)
    return [
        Passage(
            passage_id=f"tiktok-aigc-{video_id.group(1) if video_id else 'post'}",
            source=PLATFORM_AI_LABEL,
            source_kind=SourceKind.PLATFORM,
            url=HttpUrl(url),
            title="TikTok label: AI-generated",
            text=text,
            score=1.0,
        )
    ]


if __name__ == "__main__":
    import sys

    for passage in on_post(sys.argv[1] if len(sys.argv) > 1 else None):
        print(f"{passage.source}: {passage.title}\n{passage.text}\n{passage.url}\n")
