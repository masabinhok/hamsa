"""Fetch trusted articles from WordPress REST APIs into data/corpus/articles.jsonl."""

import html
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

from app.pipeline.contracts import SourceKind

USER_AGENT = "hamsa-corpus/0.1 (+https://github.com/masabinhok/hamsa)"
PAGE_SIZE = 100
NEPALI_TERMS = ("बाढी", "पहिरो", "डुबान", "हिमताल")
ENGLISH_TERMS = ("flood", "landslide", "GLOF", "inundation")


@dataclass(frozen=True)
class WordPressSource:
    name: str
    base_url: str
    kind: SourceKind
    language: str
    terms: tuple[str, ...]
    # Fact-checkers are fetched without a start date: a recycled clip is often
    # debunked years before it resurfaces.
    all_time: bool = False


SOURCES = (
    WordPressSource(
        "Onlinekhabar", "https://www.onlinekhabar.com", SourceKind.NEWS, "ne", NEPALI_TERMS
    ),
    WordPressSource(
        "Onlinekhabar English",
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
