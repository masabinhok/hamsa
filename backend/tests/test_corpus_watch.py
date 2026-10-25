from collections.abc import Sequence
from datetime import date
from pathlib import Path

import httpx
from qdrant_client import QdrantClient

from app.corpus.__main__ import read_articles, refresh
from app.corpus.fetch import RssSource, fetch_feed
from app.pipeline.contracts import SourceKind
from app.pipeline.retrieve import EMBEDDING_DIM, EvidenceStore

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>बुढीगण्डकीमा बाढी</title><link>https://techpana.com/2026/1/budhigandaki-flood</link>
<pubDate>Sun, 11 Oct 2026 08:00:00 +0545</pubDate>
<description>&lt;p&gt;गोरखामा बाढीले पुल बगायो।&lt;/p&gt;</description></item>
<item><title>फ्याक्टचेक: भिडियो पुरानो</title>
<link>https://techpana.com/2026/2/fact-check-old-video-shared-as-new</link>
<pubDate>Mon, 12 Oct 2026 09:00:00 +0000</pubDate>
<description>राजनीतिक दाबी भ्रामक छ।</description></item>
<item><title>नयाँ स्मार्टफोन</title><link>https://techpana.com/2026/3/new-phone</link>
<pubDate>Mon, 12 Oct 2026 10:00:00 +0000</pubDate><description>फोनको समीक्षा।</description></item>
<item><title>No date</title><link>https://techpana.com/2026/4/flood</link>
<description>flood</description></item>
</channel></rss>"""

TECHPANA = RssSource("Techpana", "https://techpana.com/feed", "ne", ("fact-check",))


def serve(request: httpx.Request) -> httpx.Response:
    if str(request.url) == TECHPANA.feed_url:
        return httpx.Response(200, content=FEED.encode())
    if "wp-json" in str(request.url):
        return httpx.Response(200, json=[], headers={"x-wp-totalpages": "1"})
    return httpx.Response(404)  # an unreachable feed must not stop the others


def test_feed_keeps_disaster_news_and_every_fact_check() -> None:
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        articles = list(fetch_feed(client, TECHPANA))
    assert [(a.title, a.source_kind) for a in articles] == [
        ("बुढीगण्डकीमा बाढी", SourceKind.NEWS),
        ("फ्याक्टचेक: भिडियो पुरानो", SourceKind.FACT_CHECK),
    ]
    assert articles[0].text == "गोरखामा बाढीले पुल बगायो।"
    assert articles[0].published_at.isoformat() == "2026-10-11T08:00:00+05:45"


def fake_embed(texts: Sequence[str]) -> list[list[float]]:
    return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]


def test_refresh_indexes_only_articles_it_has_not_seen(tmp_path: Path) -> None:
    store = EvidenceStore(QdrantClient(":memory:"))
    path = tmp_path / "articles.jsonl"
    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        first = refresh(client, store, fake_embed, path, date(2026, 10, 10))
        second = refresh(client, store, fake_embed, path, date(2026, 10, 10))
    assert first == 2
    assert second == 0
    assert len(read_articles(path)) == 2
