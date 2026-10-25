"""Build and keep the evidence corpus current, from backend/:

uv run python -m app.corpus fetch [--since 2026-08-20]   # articles -> data/corpus/articles.jsonl
uv run python -m app.corpus index                        # rebuild Qdrant from the articles
uv run python -m app.corpus watch                        # add new articles every 15 minutes
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx
from qdrant_client import QdrantClient

from app.config import REPO_ROOT, get_settings
from app.corpus.fetch import FEEDS, SOURCES, USER_AGENT, Article, fetch_feed, fetch_source
from app.llm.ollama import OllamaClient
from app.pipeline.retrieve import EmbedText, EvidenceStore

ARTICLES = REPO_ROOT / "data" / "corpus" / "articles.jsonl"
# Ollama embeds one input at a time per request; 4 concurrent requests measured 4x faster
# on the target GPU (6 -> 25 passages/s).
PARALLEL_REQUESTS = 4
ARTICLES_PER_BATCH = 32
WATCH_EVERY_S = 15 * 60
# The watch loop asks WordPress sources only for recent posts; older ones are known.
WATCH_LOOKBACK = timedelta(days=2)


def http_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True)


def collect(client: httpx.Client, since: date) -> dict[str, Article]:
    """Articles from every source by URL; one unreachable source does not stop the rest."""
    by_url: dict[str, Article] = {}
    for name, articles in [
        *((s.base_url, lambda s=s: fetch_source(client, s, since)) for s in SOURCES),
        *((f.feed_url, lambda f=f: fetch_feed(client, f)) for f in FEEDS),
    ]:
        before = len(by_url)
        try:
            for article in articles():
                by_url.setdefault(str(article.url), article)
        except (httpx.HTTPError, ET.ParseError, ValueError) as error:
            print(f"  {name}: skipped ({type(error).__name__}: {error})")
            continue
        print(f"  {name}: {len(by_url) - before} articles")
    return by_url


def fetch(since: date) -> int:
    ARTICLES.parent.mkdir(parents=True, exist_ok=True)
    with http_client() as client:
        by_url = collect(client, since)
    with ARTICLES.open("w", encoding="utf-8") as handle:
        for article in sorted(by_url.values(), key=lambda a: a.published_at, reverse=True):
            handle.write(article.model_dump_json() + "\n")
    print(f"{len(by_url)} articles -> {ARTICLES.relative_to(REPO_ROOT)}")
    return 0


def read_articles(path: Path) -> list[Article]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Article.model_validate_json(line) for line in lines if line.strip()]


def refresh(
    client: httpx.Client, store: EvidenceStore, embed: EmbedText, path: Path, since: date
) -> int:
    """Fetch, keep only articles not seen before, append them, and index them in place."""
    known = {str(a.url) for a in read_articles(path)}
    new = [a for url, a in collect(client, since).items() if url not in known]
    if not new:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.writelines(a.model_dump_json() + "\n" for a in new)
    store.ensure()
    return store.add(new, embed)


def watch() -> int:
    store = EvidenceStore(QdrantClient(url=str(get_settings().qdrant_url)))
    embed = embedder()
    try:
        while True:
            with http_client() as client:
                added = refresh(client, store, embed, ARTICLES, date.today() - WATCH_LOOKBACK)
            print(f"{time.strftime('%H:%M')} added {added} passages", flush=True)
            time.sleep(WATCH_EVERY_S)
    except KeyboardInterrupt:
        return 0


def embedder() -> EmbedText:
    settings = get_settings()
    ollama = OllamaClient(str(settings.ollama_host))

    def embed_part(part: Sequence[str]) -> list[list[float]]:
        return ollama.embed(settings.embedding_model, part, batch=True)

    def embed(texts: Sequence[str]) -> list[list[float]]:
        size = -(-len(texts) // PARALLEL_REQUESTS)
        parts = [texts[i : i + size] for i in range(0, len(texts), size)]
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as pool:
            results = pool.map(embed_part, parts)
        return [vector for part in results for vector in part]

    return embed


def index() -> int:
    articles = read_articles(ARTICLES)
    store = EvidenceStore(QdrantClient(url=str(get_settings().qdrant_url)))
    store.recreate()
    embed = embedder()
    started, added = time.monotonic(), 0
    for start in range(0, len(articles), ARTICLES_PER_BATCH):
        added += store.add(articles[start : start + ARTICLES_PER_BATCH], embed)
        done = min(start + ARTICLES_PER_BATCH, len(articles))
        rate = added / max(time.monotonic() - started, 1e-6)
        print(f"\r  {done}/{len(articles)} articles, {added} passages, {rate:.1f}/s", end="")
    print(f"\nindexed {added} passages from {len(articles)} articles")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the evidence corpus.")
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_cmd = commands.add_parser("fetch")
    fetch_cmd.add_argument(
        "--since",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=30),
    )
    commands.add_parser("index")
    commands.add_parser("watch")
    args = parser.parse_args()
    if args.command == "fetch":
        return fetch(args.since)
    return index() if args.command == "index" else watch()


if __name__ == "__main__":
    sys.exit(main())
