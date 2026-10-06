import hashlib
import re
from collections.abc import Sequence
from datetime import date, datetime

import numpy as np
import pytest
from qdrant_client import QdrantClient

from app.corpus.fetch import Article
from app.pipeline.contracts import SourceKind
from app.pipeline.retrieve import (
    EMBEDDING_DIM,
    MAX_PASSAGES,
    MAX_PER_ARTICLE,
    MAX_PER_SOURCE,
    EvidenceStore,
    chunk,
    passage_id,
    queries_for,
    retrieve,
)
from tests.factories import claim

INCIDENT = date(2026, 8, 26)


def fake_embed(texts: Sequence[str]) -> list[list[float]]:
    """Hashed bag of words: texts sharing words get high cosine, like a real embedder."""
    vectors: list[list[float]] = []
    for text in texts:
        vector = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        for word in re.findall(r"\w+", text.lower()):
            digest = hashlib.md5(word.encode(), usedforsecurity=False).digest()
            vector[int.from_bytes(digest[:4], "little") % EMBEDDING_DIM] += 1.0
        vectors.append((vector / (np.linalg.norm(vector) or 1.0)).tolist())
    return vectors


def article(
    slug: str,
    text: str,
    published: str,
    kind: SourceKind = SourceKind.NEWS,
    source: str | None = None,
) -> Article:
    default_source = "Nepal Factcheck" if kind is SourceKind.FACT_CHECK else f"Outlet {slug}"
    return Article.model_validate(
        {
            "url": f"https://news.test/{slug}",
            "source": source or default_source,
            "source_kind": kind,
            "language": "en",
            "title": slug,
            "published_at": datetime.fromisoformat(published),
            "text": text,
        }
    )


@pytest.fixture
def store() -> EvidenceStore:
    evidence = EvidenceStore(QdrantClient(":memory:"))
    evidence.recreate()
    return evidence


# chunking


def test_short_paragraphs_are_packed_up_to_the_limit() -> None:
    assert chunk("a\nb\nc", limit=3) == ["a\nb", "c"]


def test_long_paragraph_splits_at_danda_and_full_stop() -> None:
    first = "पहिलो वाक्य। दोस्रो वाक्य।"
    text = f"{first} Third sentence."
    assert chunk(text, limit=len(first)) == [first, "Third sentence."]


def test_sentence_longer_than_limit_is_hard_split_not_dropped() -> None:
    assert chunk("x" * 25, limit=10) == ["x" * 10, "x" * 10, "x" * 5]


def test_passage_ids_are_stable_per_url_and_index() -> None:
    assert passage_id("https://a.test/1", 0) == passage_id("https://a.test/1", 0)
    assert passage_id("https://a.test/1", 0) != passage_id("https://a.test/1", 1)


# queries


def test_queries_include_visible_text_and_skip_duplicates() -> None:
    c = claim(
        claim="Flood in Rasuwa",
        claim_en="Flood in Rasuwa",
        visible_text=["Columbia Glacier", "weather.gov"],
    )
    assert queries_for(c) == ["Flood in Rasuwa", "Columbia Glacier weather.gov"]


# retrieval


def test_retrieves_the_matching_fact_check_first(store: EvidenceStore) -> None:
    store.add(
        [
            article(
                "debunk",
                "viral Rasuwa glacier video is Columbia Glacier Alaska",
                "2026-08-28T09:00:00",
                SourceKind.FACT_CHECK,
            ),
            article("budget", "parliament passes the annual budget", "2026-08-28T09:00:00"),
        ],
        fake_embed,
    )
    c = claim(claim_en="Rasuwa flood video glacier", visible_text=["Columbia Glacier"])

    evidence = retrieve(c, store, fake_embed, since=INCIDENT)

    assert evidence.passages[0].source_kind is SourceKind.FACT_CHECK
    assert str(evidence.passages[0].url) == "https://news.test/debunk"


def test_news_before_the_incident_is_excluded_but_old_fact_checks_count(
    store: EvidenceStore,
) -> None:
    store.add(
        [
            article("old-news", "Melamchi flood swept the bazaar", "2021-06-16T09:00:00"),
            article(
                "old-check",
                "Melamchi flood video is from 2021",
                "2023-07-01T09:00:00",
                SourceKind.FACT_CHECK,
            ),
            article("new-news", "Melamchi flood again", "2026-08-27T09:00:00"),
        ],
        fake_embed,
    )
    evidence = retrieve(claim(claim_en="Melamchi flood"), store, fake_embed, since=INCIDENT)
    urls = {str(p.url) for p in evidence.passages}
    assert urls == {"https://news.test/old-check", "https://news.test/new-news"}


def test_caps_passages_per_article_and_in_total(store: EvidenceStore) -> None:
    long_text = "\n".join(f"flood paragraph {i} " + "word " * 250 for i in range(6))
    store.add(
        [article(f"a{i}", long_text, "2026-08-27T09:00:00") for i in range(6)],
        fake_embed,
    )
    evidence = retrieve(claim(claim_en="flood paragraph"), store, fake_embed, since=INCIDENT)

    per_url: dict[str, int] = {}
    for p in evidence.passages:
        per_url[str(p.url)] = per_url.get(str(p.url), 0) + 1
    assert len(evidence.passages) == MAX_PASSAGES
    assert max(per_url.values()) <= MAX_PER_ARTICLE


def test_empty_corpus_gives_empty_evidence(store: EvidenceStore) -> None:
    assert retrieve(claim(), store, fake_embed, since=INCIDENT).passages == []


def test_one_publisher_cannot_fill_the_evidence(store: EvidenceStore) -> None:
    prolific = [
        article(
            f"ok{i}", f"Rasuwa flood cause report {i}", "2026-08-27T09:00:00", source="Onlinekhabar"
        )
        for i in range(6)
    ]
    other = article("np", "Rasuwa flood cause", "2026-08-27T09:00:00", source="Nepalnews")
    store.add([*prolific, other], fake_embed)

    evidence = retrieve(claim(claim_en="Rasuwa flood cause"), store, fake_embed, since=INCIDENT)

    sources = [p.source for p in evidence.passages]
    assert sources.count("Onlinekhabar") == MAX_PER_SOURCE
    assert "Nepalnews" in sources


def test_passages_carry_their_headline(store: EvidenceStore) -> None:
    store.add([article("debunk", "flood video is from Alaska", "2026-08-28T09:00:00")], fake_embed)
    [found] = retrieve(claim(claim_en="flood video"), store, fake_embed, since=INCIDENT).passages
    assert found.title == "debunk"
