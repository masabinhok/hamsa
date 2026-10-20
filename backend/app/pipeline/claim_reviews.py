"""Published fact-checks from anywhere, via Google's Fact Check Tools API (ADR 0012).

Most viral fakes about Nepal's disasters are debunked first by fact-checkers abroad
(AFP, Boom, Alt News, Newschecker), whose sites the corpus does not fetch. Their articles
carry ClaimReview markup, which this API indexes. It is a search index, not a model.
"""

import hashlib
import logging
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import ValidationError

from app.pipeline.contracts import Claim, Evidence, Passage, SourceKind
from app.pipeline.retrieve import MAX_PASSAGES, RRF_K

API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
PAGE_SIZE = 10
MAX_REVIEWS = 2  # of the 8 evidence slots; the rest stay with the trusted corpus
QUERY_CHARS = 300
# The index matches keywords, so a whole claim sentence finds almost nothing. On the
# eval (2026-10-20) full sentences found 1 of 19 fact-checks; 12, 8 and 5 words each
# found different ones, so all three are searched and their rankings fused.
QUERY_WORDS = (12, 8, 5)
log = logging.getLogger("hamsa.claim_reviews")

FindReviews = Callable[[Claim], list[Passage]]


def review_queries(claim: Claim) -> list[str]:
    """The English claim's opening words, and the on-screen text, which often names the
    true origin. Fact-checkers abroad write in English, so the Nepali claim is not searched.
    """
    words = claim.claim_en.split()
    queries = [" ".join(words[:n])[:QUERY_CHARS] for n in QUERY_WORDS]
    if claim.visible_text:
        queries.append(" ".join(claim.visible_text)[:QUERY_CHARS])
    return list(dict.fromkeys(q for q in queries if q.strip()))


def parse(data: dict[str, Any]) -> list[Passage]:
    """One passage per review, worded so the verdict model sees what was claimed and rated."""
    passages: list[Passage] = []
    for claim in data.get("claims", []):
        reviewed = str(claim.get("text", "")).strip()
        claimant = f" by {claim['claimant']}" if claim.get("claimant") else ""
        when = f" ({str(claim['claimDate'])[:10]})" if claim.get("claimDate") else ""
        for review in claim.get("claimReview", []):
            publisher: dict[str, Any] = review.get("publisher", {})
            url = str(review.get("url", ""))
            rating = str(review.get("textualRating", "")).strip() or "not stated"
            digest = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
            fields = {
                "passage_id": f"fc-{digest}",
                "source": publisher.get("name") or publisher.get("site") or "fact-checker",
                "source_kind": SourceKind.FACT_CHECK,
                "url": url,
                "title": review.get("title"),
                "published_at": review.get("reviewDate"),
                "text": f'Fact-check of the claim "{reviewed}"{claimant}{when}. Rating: {rating}.',
                "score": 0.0,  # not ranked against the corpus; reviews always go first
            }
            try:
                passages.append(Passage.model_validate(fields))
            except ValidationError:
                continue  # a review without a usable link or text is no evidence
    return passages


class ClaimReviewSearch:
    """Never raises: when the search is down the case goes on with corpus evidence."""

    def __init__(self, api_key: str, http: httpx.Client | None = None) -> None:
        self._http = http or httpx.Client(timeout=10)
        # A header, not ?key=: request URLs are logged, and the key must not be.
        self._headers = {"X-Goog-Api-Key": api_key}

    def __call__(self, claim: Claim) -> list[Passage]:
        """Reviews ranked by reciprocal rank fusion, so one found by several queries leads."""
        found: dict[str, Passage] = {}
        scores: dict[str, float] = {}
        for query in review_queries(claim):
            try:
                response = self._http.get(
                    API, params={"query": query, "pageSize": PAGE_SIZE}, headers=self._headers
                )
                response.raise_for_status()
                passages = parse(response.json())
            except (httpx.HTTPError, ValueError) as error:
                log.warning("fact-check search failed: %s", type(error).__name__)
                break
            for rank, passage in enumerate(passages):
                url = str(passage.url)
                found.setdefault(url, passage)
                scores[url] = scores.get(url, 0.0) + 1.0 / (RRF_K + rank + 1)
        return [found[url] for url in sorted(found, key=lambda u: scores[u], reverse=True)]


def add_reviews(evidence: Evidence, reviews: list[Passage]) -> Evidence:
    """Put the first new reviews ahead of the corpus passages, keeping at most 8."""
    known = {str(p.url) for p in evidence.passages}
    picked = [r for r in reviews if str(r.url) not in known][:MAX_REVIEWS]
    return Evidence(passages=(picked + evidence.passages)[:MAX_PASSAGES])
