"""Fetch trusted articles from WordPress REST APIs and RSS feeds."""

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

from app.pipeline.contracts import SourceKind

USER_AGENT = "hamsa-corpus/0.1 (+https://github.com/masabinhok/hamsa)"
PAGE_SIZE = 100
# Any disaster, not one event: floods, landslides (हिमपहिरो matches पहिरो), glacial lakes,
# earthquakes, wildfires, fires, lightning.
NEPALI_TERMS = ("बाढी", "पहिरो", "डुबान", "हिमताल", "भूकम्प", "डढेलो", "आगलागी", "चट्याङ")
ENGLISH_TERMS = ("flood", "landslide", "GLOF", "inundation", "earthquake", "avalanche", "wildfire")
RSS_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"


@dataclass(frozen=True)
class WordPressSource:
    # The publisher. Independence of sources is judged per publisher, so editions of
    # one outlet (Nepali and English Onlinekhabar) share a name.
    name: str
    base_url: str
    kind: SourceKind
    language: str
    terms: tuple[str, ...]
    # Fact-checkers are fetched without a start date: a recycled clip is often
    # debunked years before it resurfaces.
    all_time: bool = False


@dataclass(frozen=True)
class RssSource:
    """A feed lists only its latest items, so it suits `corpus watch`, not a backfill."""

    name: str
    feed_url: str
    language: str
    # A link containing one of these is the publisher's own fact-check.
    fact_check_marks: tuple[str, ...] = ()


FEEDS = (
    RssSource("Techpana", "https://techpana.com/feed", "ne", ("fact-check", "factcheck")),
    RssSource("Ratopati", "https://ratopati.com/feed", "ne"),
    RssSource("Setopati", "https://www.setopati.com/feed", "ne"),
)

SOURCES = (
    WordPressSource(
        "Onlinekhabar", "https://www.onlinekhabar.com", SourceKind.NEWS, "ne", NEPALI_TERMS
    ),
    WordPressSource(
        "Onlinekhabar",
        "https://english.onlinekhabar.com",
        SourceKind.NEWS,
        "en",
        ENGLISH_TERMS,
    ),
    WordPressSource("Nepalnews", "https://nepalnews.com", SourceKind.NEWS, "ne", NEPALI_TERMS),
    WordPressSource(
        "Nepal Factcheck",
        "https://nepalfactcheck.org",
        SourceKind.FACT_CHECK,
        "ne",
        NEPALI_TERMS + ENGLISH_TERMS,
        all_time=True,
    ),
)


class Article(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: HttpUrl
    source: str
    source_kind: SourceKind
    language: str
    title: str
    published_at: datetime
    text: str


class _TextExtractor(HTMLParser):
    BLOCKS = frozenset(
        {
            "p",
            "div",
            "br",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "tr",
            "figcaption",
        }
    )
    SKIP = frozenset({"script", "style", "noscript", "iframe", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skipping += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skipping:
            self._skipping -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipping:
            self.parts.append(data)


def html_to_text(markup: str) -> str:
    """Article HTML to plain text, one paragraph per line."""
    extractor = _TextExtractor()
    extractor.feed(markup)
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(extractor.parts).split("\n"))
    return "\n".join(line for line in lines if line)


def mentions_disaster(text: str) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in NEPALI_TERMS + ENGLISH_TERMS)


def fetch_feed(client: httpx.Client, source: RssSource) -> Iterator[Article]:
    """Disaster news and every fact-check from one feed.

    shortcut: a feed item carries the headline and lead, not the whole article; fetch the
    page if evidence from feeds proves too thin.
    """
    response = client.get(source.feed_url)
    response.raise_for_status()
    # Feeds come from a fixed list of outlets, and Python's expat (2.4.1+) refuses entity
    # expansion attacks.
    root = ET.fromstring(response.content)  # noqa: S314
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        title = html.unescape(html_to_text(item.findtext("title") or ""))
        text = html_to_text(item.findtext(RSS_CONTENT) or item.findtext("description") or "")
        published = item.findtext("pubDate")
        if not (link and text and published):
            continue
        try:
            url = HttpUrl(link)
        except ValueError:
            continue
        fact_check = any(mark in link for mark in source.fact_check_marks)
        if not fact_check and not mentions_disaster(f"{title}\n{text}"):
            continue
        yield Article(
            url=url,
            source=source.name,
            source_kind=SourceKind.FACT_CHECK if fact_check else SourceKind.NEWS,
            language=source.language,
            title=title,
            published_at=parsedate_to_datetime(published),
            text=text,
        )


def fetch_source(client: httpx.Client, source: WordPressSource, since: date) -> Iterator[Article]:
    """Every post matching any term, newest first, each yielded once."""
    seen: set[int] = set()
    for term in source.terms:
        for post in _paginate(client, source, term, since):
            post_id: int = post["id"]
            if post_id in seen:
                continue
            seen.add(post_id)
            text = html_to_text(post["content"]["rendered"])
            if not text:
                continue
            yield Article(
                url=post["link"],
                source=source.name,
                source_kind=source.kind,
                language=source.language,
                title=html.unescape(html_to_text(post["title"]["rendered"])),
                published_at=datetime.fromisoformat(post["date"]),
                text=text,
            )


def _paginate(
    client: httpx.Client, source: WordPressSource, term: str, since: date
) -> Iterator[dict[str, Any]]:
    params: dict[str, str | int] = {
        "search": term,
        "per_page": PAGE_SIZE,
        "_fields": "id,date,link,title,content",
    }
    if not source.all_time:
        params["after"] = f"{since.isoformat()}T00:00:00"
    page = 1
    while True:
        response = client.get(
            f"{source.base_url}/wp-json/wp/v2/posts", params=params | {"page": page}
        )
        # WordPress answers 400 for a page past the end.
        if response.status_code == 400 and page > 1:
            return
        response.raise_for_status()
        posts: list[dict[str, Any]] = response.json()
        yield from posts
        if page >= int(response.headers.get("x-wp-totalpages", "1")):
            return
        page += 1
