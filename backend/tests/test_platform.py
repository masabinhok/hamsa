import json
from typing import Any

import httpx

from app.pipeline.contracts import SourceKind
from app.pipeline.platform import on_post

NOTE: dict[str, Any] = {
    "birdwatch_pivot": {
        "destinationUrl": "https://twitter.com/i/birdwatch/n/42",
        "title": "Readers added context they thought people might want to know",
        "noteId": "42",
        "subtitle": {
            "text": "The video compiles clips from prior unrelated incidents. \n\naap.com.au/…",
            "entities": [{"ref": {"url": {"url": "https://t.co/abc", "urlType": "ExternalUrl"}}}],
        },
    }
}


def client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


def x_api(body: dict[str, Any], seen: list[httpx.Request]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "t.co":
            return httpx.Response(
                301, headers={"location": "https://www.aap.com.au/factcheck/fake"}
            )
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handle)


def test_a_community_note_becomes_a_platform_passage_with_its_real_links() -> None:
    seen: list[httpx.Request] = []
    [note] = on_post("https://x.com/someone/status/123?s=20", client(x_api(NOTE, seen)))
    assert note.source_kind is SourceKind.PLATFORM
    assert note.source == "X Community Notes"
    assert str(note.url) == "https://twitter.com/i/birdwatch/n/42"
    assert note.text.startswith("The video compiles clips")
    assert "https://www.aap.com.au/factcheck/fake" in note.text
    first = seen[0]
    assert first.url.params["id"] == "123"
    assert "token" in first.url.params  # without one X leaves the note out
    assert seen[1].method == "HEAD"  # the link target itself is never fetched


def test_a_post_without_a_note_gives_nothing() -> None:
    assert on_post("https://x.com/someone/status/123", client(x_api({"text": "hi"}, []))) == []


def tiktok_page(labelled: bool) -> httpx.MockTransport:
    data = {"IsAigc": labelled, "AIGCDescription": "Creator labeled as AI-generated"}
    page = f"<script>{json.dumps(data)}</script>"
    return httpx.MockTransport(lambda request: httpx.Response(200, text=page))


def test_tiktoks_ai_label_is_read_from_the_page() -> None:
    [label] = on_post("https://www.tiktok.com/@a/video/7", client(tiktok_page(True)))
    assert label.source == "TikTok AI label"
    assert "Creator labeled as AI-generated" in label.text
    assert on_post("https://www.tiktok.com/@a/video/7", client(tiktok_page(False))) == []


def test_other_links_and_failures_give_nothing() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    assert on_post("https://github.com/a/b", client(httpx.MockTransport(broken))) == []
    assert on_post(None) == []
    assert on_post("https://x.com/a/status/1", client(httpx.MockTransport(broken))) == []
    assert on_post("https://x.com/a/status/1", client(httpx.MockTransport(garbage))) == []
    assert on_post("https://www.youtube.com/watch?v=x", client(httpx.MockTransport(broken))) == []


def test_what_the_post_shows_comes_first_within_the_eight_slots() -> None:
    from app.pipeline.contracts import Evidence
    from app.pipeline.run import add_on_post
    from tests.factories import passage

    corpus = Evidence(passages=[passage(f"p{i}", f"Outlet {i}") for i in range(8)])
    note = passage("note-1", "X Community Notes", source_kind="platform")
    ids = [p.passage_id for p in add_on_post(corpus, [note]).passages]
    assert ids == ["note-1", *[f"p{i}" for i in range(7)]]
