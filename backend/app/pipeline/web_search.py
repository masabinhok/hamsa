"""Evidence from the open web, searched per case through self-hosted SearXNG.

The trusted corpus holds a few Nepali outlets, so a claim about tourists, or an event
those outlets did not cover, found nothing (field test, 2026-10-22). Web pages are
untrusted: they are shown to the verdict model and the checker as `web` evidence, and
the router never counts them as independent sources for a fast-track.
"""

import hashlib
import logging
import math
from collections.abc import Callable, Sequence
from datetime import date, datetime
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.corpus.fetch import USER_AGENT, html_to_text
from app.ingest.download import meta_tags
from app.pipeline.contracts import Claim, Evidence, Passage, SourceKind
from app.pipeline.retrieve import MAX_PASSAGES, EmbedText, chunk

QUERY_CHARS = 200
MAX_PAGES = 6  # fetched per case; each costs a request and a few embeddings on the CPU
CHUNKS_PER_PAGE = 12  # the opening of an article carries its facts
MAX_WEB_PASSAGES = 2  # of the 8 evidence slots; the rest stay with fact-checks and the corpus
# bge-m3 cosine between the claim and a page's best chunk. On three real claims
# (2026-10-22) on-topic pages scored 0.67-0.76, off-topic ones (a Philippines prayer video,
# a consent page) 0.25-0.37.
MIN_SIMILARITY = 0.6
log = logging.getLogger("hamsa.web_search")

FindWeb = Callable[[Claim, date, date | None], list[Passage]]


def query_for(claim: Claim) -> str:
    return " ".join([claim.claim_en, *claim.places])[:QUERY_CHARS]


def _published(tags: dict[str, str], listed: str | None) -> date | None:
    for raw in (tags.get("article:published_time"), listed):
        if raw:
            try:
                return datetime.fromisoformat(raw).date()
            except ValueError:
                continue
    return None


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class WebSearch:
    """Never raises: when search or a page fails, the case goes on without it."""

    def __init__(self, base_url: str, embed: EmbedText, http: httpx.Client | None = None) -> None:
        self._search = f"{base_url.rstrip('/')}/search"
        self._embed = embed
        self._http = http or httpx.Client(
            timeout=10, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )

    def __call__(self, claim: Claim, since: date, until: date | None) -> list[Passage]:
        """The best passage of each dated page in the news window, most similar first."""
        try:
            response = self._http.get(
                self._search,
                params={"q": query_for(claim), "format": "json", "categories": "news"},
            )
            response.raise_for_status()
            results: list[dict[str, str]] = response.json().get("results", [])
        except (httpx.HTTPError, ValueError) as error:
            log.warning("web search failed: %s", type(error).__name__)
            return []

        [target] = self._embed([claim.claim_en])
        found: list[Passage] = []
        for result in results[:MAX_PAGES]:
            if passage := self._passage(result, target, since, until):
                found.append(passage)
        found.sort(key=lambda p: p.score, reverse=True)
        return found[:MAX_WEB_PASSAGES]

    def _passage(
        self, result: dict[str, str], target: list[float], since: date, until: date | None
    ) -> Passage | None:
        url = result.get("url", "")
        try:
            page = self._http.get(url)
            page.raise_for_status()
        except httpx.HTTPError:
            return None
        tags = meta_tags(page.text)
        published = _published(tags, result.get("publishedDate"))
        # Figures change daily, so an undated page cannot speak for the post's date.
        if published is None or published < since or (until and published > until):
            return None
        chunks = chunk(html_to_text(page.text))[:CHUNKS_PER_PAGE]
        if not chunks:
            return None
        scored = [
            (_cosine(target, vector), text)
            for vector, text in zip(self._embed(chunks), chunks, strict=True)
        ]
        score, text = max(scored)
        if score < MIN_SIMILARITY:
            return None
        digest = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
        try:
            return Passage.model_validate(
                {
                    "passage_id": f"web-{digest}",
                    "source": tags.get("og:site_name") or urlsplit(url).netloc.removeprefix("www."),
                    "source_kind": SourceKind.WEB,
                    "url": url,
                    "title": tags.get("og:title") or result.get("title"),
                    "published_at": datetime.combine(published, datetime.min.time()),
                    "text": text,
                    "score": round(score, 5),
                }
            )
        except ValidationError:
            return None


def add_web(evidence: Evidence, found: list[Passage]) -> Evidence:
    """Web passages take the last slots, after fact-checks and the trusted corpus."""
    known = {str(p.url) for p in evidence.passages}
    web = [p for p in found if str(p.url) not in known][:MAX_WEB_PASSAGES]
    return Evidence(passages=[*evidence.passages[: MAX_PASSAGES - len(web)], *web])
