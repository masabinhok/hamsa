"""Evidence retrieval (architecture 3.5): bge-m3 over the trusted corpus in Qdrant."""

import hashlib
import re
import uuid
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from qdrant_client import QdrantClient, models

from app.corpus.fetch import Article
from app.pipeline.contracts import Claim, Evidence, Passage, SourceKind

COLLECTION = "evidence_passages"
EMBEDDING_DIM = 1024  # bge-m3 dense
CHUNK_CHARS = 1200  # roughly 300 tokens of English; Nepali runs longer per token
MAX_PASSAGES = 8
MAX_PER_ARTICLE = 2
# Without this, one prolific outlet filled 7 of 8 slots for the Rasuwa claim and
# crowded out other sources; independence is judged per publisher.
MAX_PER_SOURCE = 3
CANDIDATES_PER_QUERY = 20
# News older than this before the claim is about an earlier event, e.g. 2024 Melamchi
# reports for a 2026 Melamchi claim.
NEWS_WINDOW = timedelta(days=30)
RRF_K = 60  # standard reciprocal-rank-fusion constant
VISIBLE_TEXT_CHARS = 500

EmbedText = Callable[[Sequence[str]], list[list[float]]]


def chunk(text: str, limit: int = CHUNK_CHARS) -> list[str]:
    """Paragraph-aligned chunks of at most `limit` chars; long paragraphs split at sentences."""
    pieces: list[str] = []
    for paragraph in text.split("\n"):
        if len(paragraph) <= limit:
            pieces.append(paragraph)
            continue
        # Nepali ends sentences with the danda (।).
        sentences = re.split(r"(?<=[।.!?])\s+", paragraph)
        pieces.extend(_pack(sentences, limit, " "))
    return [c for c in _pack(pieces, limit, "\n") if c.strip()]


def _pack(parts: Sequence[str], limit: int, joiner: str) -> Iterator[str]:
    current = ""
    for part in parts:
        candidate = f"{current}{joiner}{part}" if current else part
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            yield current
        # A single sentence over the limit is hard-split rather than dropped.
        while len(part) > limit:
            yield part[:limit]
            part = part[limit:]
        current = part
    if current:
        yield current


def passage_id(url: str, index: int) -> str:
    return f"{hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]}-{index}"


class EvidenceStore:
    def __init__(self, client: QdrantClient, collection: str = COLLECTION) -> None:
        self._client = client
        self._collection = collection

    def recreate(self) -> None:
        if self._client.collection_exists(self._collection):
            self._client.delete_collection(self._collection)
        self._create()

    def ensure(self) -> None:
        """Create the collection unless it exists; `corpus watch` adds to it in place."""
        if not self._client.collection_exists(self._collection):
            self._create()

    def _create(self) -> None:
        self._client.create_collection(
            self._collection,
            vectors_config=models.VectorParams(size=EMBEDDING_DIM, distance=models.Distance.COSINE),
        )
        for field, schema in (
            ("published_ts", models.PayloadSchemaType.INTEGER),
            ("source_kind", models.PayloadSchemaType.KEYWORD),
        ):
            self._client.create_payload_index(self._collection, field, schema)

    def add(self, articles: Sequence[Article], embed: EmbedText) -> int:
        """Chunk, embed (title prepended for context), and store. Returns passages added."""
        rows: list[tuple[str, str, Article]] = []
        for article in articles:
            for i, text in enumerate(chunk(article.text)):
                rows.append((passage_id(str(article.url), i), text, article))
        if not rows:
            return 0
        vectors = embed([f"{article.title}\n{text}" for _, text, article in rows])
        self._client.upsert(
            self._collection,
            points=[
                models.PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, pid)),
                    vector=vector,
                    payload={
                        "passage_id": pid,
                        "source": article.source,
                        "source_kind": article.source_kind.value,
                        "url": str(article.url),
                        "title": article.title,
                        "published_at": article.published_at.isoformat(),
                        "published_ts": int(article.published_at.timestamp()),
                        "text": text,
                    },
                )
                for (pid, text, article), vector in zip(rows, vectors, strict=True)
            ],
        )
        return len(rows)

    def search(self, vector: list[float], since: date) -> list[dict[str, Any]]:
        """Nearest passages published since `since`, or fact-checks of any date."""
        since_ts = int(datetime.combine(since, time.min, tzinfo=UTC).timestamp())
        response = self._client.query_points(
            self._collection,
            query=vector,
            limit=CANDIDATES_PER_QUERY,
            with_payload=True,
            query_filter=models.Filter(
                should=[
                    models.FieldCondition(key="published_ts", range=models.Range(gte=since_ts)),
                    models.FieldCondition(
                        key="source_kind",
                        match=models.MatchValue(value=SourceKind.FACT_CHECK.value),
                    ),
                ]
            ),
        )
        return [dict(point.payload or {}) for point in response.points]


def queries_for(claim: Claim) -> list[str]:
    """Original-language claim, English claim, and on-screen text, which often names the
    real origin (e.g. "Columbia Glacier")."""
    queries = [claim.claim, claim.claim_en]
    if claim.visible_text:
        queries.append(" ".join(claim.visible_text)[:VISIBLE_TEXT_CHARS])
    return list(dict.fromkeys(queries))


def news_since(claim: Claim, seen_on: date) -> date:
    """Start of the news window: a month before the date the claim is about.

    Any disaster, past or upcoming: no deployment is tied to one event. Reports about an
    event appear after it, so the window has no end; fact-checks of any date always count.
    """
    return (claim.claimed_date or seen_on) - NEWS_WINDOW


def retrieve(claim: Claim, store: EvidenceStore, embed: EmbedText, since: date) -> Evidence:
    queries = queries_for(claim)
    scores: dict[str, float] = {}
    payloads: dict[str, dict[str, Any]] = {}
    for vector in embed(queries):
        for rank, payload in enumerate(store.search(vector, since)):
            pid: str = payload["passage_id"]
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (RRF_K + rank + 1)
            payloads[pid] = payload

    passages: list[Passage] = []
    per_article: dict[str, int] = {}
    per_source: dict[str, int] = {}
    for pid in sorted(scores, key=lambda p: scores[p], reverse=True):
        payload = payloads[pid]
        url: str = payload["url"]
        source: str = payload["source"]
        if (
            per_article.get(url, 0) >= MAX_PER_ARTICLE
            or per_source.get(source, 0) >= MAX_PER_SOURCE
        ):
            continue
        per_article[url] = per_article.get(url, 0) + 1
        per_source[source] = per_source.get(source, 0) + 1
        passages.append(
            Passage.model_validate(
                {
                    "passage_id": pid,
                    "source": payload["source"],
                    "source_kind": payload["source_kind"],
                    "url": url,
                    "title": payload.get("title"),
                    "published_at": payload["published_at"],
                    "text": payload["text"],
                    "score": round(scores[pid], 5),
                }
            )
        )
        if len(passages) == MAX_PASSAGES:
            break
    return Evidence(passages=passages)
