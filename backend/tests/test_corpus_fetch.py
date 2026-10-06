import json
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx

from app.corpus.fetch import WordPressSource, fetch_source, html_to_text
from app.pipeline.contracts import SourceKind


def test_html_to_text_keeps_paragraphs_and_drops_scripts() -> None:
    markup = (
        "<p>पहिलो &amp; अनुच्छेद</p><script>track()</script>"
        "<p>second<br>line</p><figure><figcaption>Photo: NDRRMA</figcaption></figure>"
    )
    assert html_to_text(markup) == "पहिलो & अनुच्छेद\nsecond\nline\nPhoto: NDRRMA"


def post(post_id: int, content: str = "<p>बाढी आयो</p>") -> dict[str, Any]:
    return {
        "id": post_id,
        "date": "2026-08-27T10:00:00",
        "link": f"https://news.test/{post_id}",
        "title": {"rendered": f"Title &amp; {post_id}"},
        "content": {"rendered": content},
    }


class FakeWordPress:
    def __init__(self, pages: dict[str, list[list[dict[str, Any]]]]) -> None:
        self.pages = pages
        self.queries: list[dict[str, list[str]]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        query = parse_qs(urlparse(str(request.url)).query)
        self.queries.append(query)
        term_pages = self.pages[query["search"][0]]
        page = int(query["page"][0])
        if page > len(term_pages):
            return httpx.Response(400, json={"code": "rest_post_invalid_page_number"})
        return httpx.Response(
            200,
            content=json.dumps(term_pages[page - 1]),
            headers={"x-wp-totalpages": str(len(term_pages))},
        )


def source(all_time: bool = False) -> WordPressSource:
    return WordPressSource(
        "News", "https://news.test", SourceKind.NEWS, "ne", ("बाढी", "पहिरो"), all_time
    )


def run(fake: FakeWordPress, src: WordPressSource) -> list[str]:
    with httpx.Client(transport=httpx.MockTransport(fake)) as client:
        return [a.title for a in fetch_source(client, src, date(2026, 8, 20))]


def test_paginates_every_term_and_yields_each_post_once() -> None:
    fake = FakeWordPress({"बाढी": [[post(1), post(2)], [post(3)]], "पहिरो": [[post(2), post(4)]]})
    assert run(fake, source()) == ["Title & 1", "Title & 2", "Title & 3", "Title & 4"]
    assert all(q["after"] == ["2026-08-20T00:00:00"] for q in fake.queries)


def test_all_time_sources_have_no_date_filter() -> None:
    fake = FakeWordPress({"बाढी": [[post(1)]], "पहिरो": [[]]})
    run(fake, source(all_time=True))
    assert all("after" not in q for q in fake.queries)


def test_posts_without_text_are_skipped() -> None:
    fake = FakeWordPress({"बाढी": [[post(1, content="<script>x</script>")]], "पहिरो": [[]]})
    assert run(fake, source()) == []
