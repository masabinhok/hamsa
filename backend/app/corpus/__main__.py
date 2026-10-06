"""Build the evidence corpus, from backend/:

uv run python -m app.corpus fetch [--since 2026-08-20]   # articles -> data/corpus/articles.jsonl
uv run python -m app.corpus index                        # articles -> Qdrant
"""

import argparse
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import httpx
from qdrant_client import QdrantClient

from app.config import REPO_ROOT, get_settings
from app.corpus.fetch import SOURCES, USER_AGENT, Article, fetch_source
from app.llm.ollama import OllamaClient
from app.pipeline.retrieve import EvidenceStore

ARTICLES = REPO_ROOT / "data" / "corpus" / "articles.jsonl"
# Ollama embeds one input at a time per request; 4 concurrent requests measured 4x faster
# on the target GPU (6 -> 25 passages/s).
PARALLEL_REQUESTS = 4
ARTICLES_PER_BATCH = 32


def fetch(since: date) -> int:
    ARTICLES.parent.mkdir(parents=True, exist_ok=True)
    by_url: dict[str, Article] = {}
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True
    ) as client:
        for source in SOURCES:
            before = len(by_url)
            for article in fetch_source(client, source, since):
                by_url.setdefault(str(article.url), article)
            print(f"  {source.name}: {len(by_url) - before} articles")
    with ARTICLES.open("w", encoding="utf-8") as handle:
        for article in sorted(by_url.values(), key=lambda a: a.published_at, reverse=True):
            handle.write(article.model_dump_json() + "\n")
    print(f"{len(by_url)} articles -> {ARTICLES.relative_to(REPO_ROOT)}")
    return 0


def index() -> int:
    settings = get_settings()
    articles = [
        Article.model_validate_json(line)
        for line in ARTICLES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ollama = OllamaClient(str(settings.ollama_host))
    store = EvidenceStore(QdrantClient(url=str(settings.qdrant_url)))
    store.recreate()

    def embed_part(part: Sequence[str]) -> list[list[float]]:
        return ollama.embed(settings.embedding_model, part, batch=True)

    def embed(texts: Sequence[str]) -> list[list[float]]:
        size = -(-len(texts) // PARALLEL_REQUESTS)
        parts = [texts[i : i + size] for i in range(0, len(texts), size)]
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as pool:
            results = pool.map(embed_part, parts)
        return [vector for part in results for vector in part]

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
        default=get_settings().incident_start - timedelta(days=6),
    )
    commands.add_parser("index")
    args = parser.parse_args()
    return fetch(args.since) if args.command == "fetch" else index()


if __name__ == "__main__":
    sys.exit(main())
