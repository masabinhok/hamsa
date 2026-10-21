from collections.abc import Sequence
from datetime import date

import httpx

from app.pipeline.contracts import Evidence, SourceKind
from app.pipeline.retrieve import MAX_PASSAGES
from app.pipeline.web_search import MAX_WEB_PASSAGES, WebSearch, add_web, query_for
from tests.factories import claim, passage

RESULTS = {
    "results": [
        {"url": "https://news.test/tourists", "title": "596 tourists missing"},
        {"url": "https://news.test/old", "title": "2021 Melamchi flood"},
        {"url": "https://news.test/undated", "title": "Nepal flood"},
        {"url": "https://news.test/budget", "title": "Budget passed"},
        {"url": "https://news.test/down", "title": "Unreachable"},
    ]
}


def page(published: str | None, body: str) -> str:
    meta = f'<meta property="article:published_time" content="{published}">' if published else ""
    site_name = '<meta property="og:site_name" content="News Test">'
    return f"<html><head>{meta}{site_name}</head><body><p>{body}</p></body></html>"


PAGES = {
    "/tourists": page("2026-08-28T06:00:00+00:00", "596 foreign tourists missing in Rasuwa"),
    "/old": page("2021-06-16T06:00:00+00:00", "tourists missing in Melamchi"),
    "/undated": page(None, "tourists missing in Rasuwa"),
    "/budget": page("2026-08-28T06:00:00+00:00", "parliament passes the budget"),
}


def site(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/search":
        assert request.url.params["format"] == "json"
        return httpx.Response(200, json=RESULTS)
    if request.url.path in PAGES:
        return httpx.Response(200, text=PAGES[request.url.path])
    return httpx.Response(503)


def embed(texts: Sequence[str]) -> list[list[float]]:
    # Texts about missing tourists point one way, everything else the other.
    return [[1.0, 0.0] if "tourists" in t.lower() else [0.0, 1.0] for t in texts]


def search() -> WebSearch:
    return WebSearch("http://searx.test", embed, httpx.Client(transport=httpx.MockTransport(site)))


def test_only_dated_pages_in_the_window_and_on_topic_become_web_evidence() -> None:
    found = search()(claim(claim_en="403 tourists missing"), date(2026, 7, 28), date(2026, 9, 11))
    [only] = found  # old: outside the window; undated; off-topic; unreachable
    assert str(only.url) == "https://news.test/tourists"
    assert (only.source, only.source_kind) == ("News Test", SourceKind.WEB)
    assert only.published_at is not None
    assert only.published_at.date() == date(2026, 8, 28)


def test_a_search_outage_gives_no_web_evidence() -> None:
    down = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(502)))
    assert WebSearch("http://searx.test", embed, down)(claim(), date(2026, 8, 1), None) == []


def test_query_names_the_places() -> None:
    assert (
        query_for(claim(claim_en="Flood swept homes", places=["Rasuwa"]))
        == "Flood swept homes Rasuwa"
    )


def test_web_passages_take_the_last_slots_without_duplicates() -> None:
    corpus = [passage(f"p{n}", f"Outlet {n}") for n in range(MAX_PASSAGES)]
    web = [passage(f"w{n}", f"site{n}.test", source_kind="web") for n in range(3)]
    merged = add_web(Evidence(passages=corpus), [corpus[0], *web]).passages
    assert len(merged) == MAX_PASSAGES
    assert [p.passage_id for p in merged[-MAX_WEB_PASSAGES:]] == ["w0", "w1"]
