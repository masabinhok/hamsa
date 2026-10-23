import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.messenger import Messenger, create_app, signed, submissions
from app.store.cases import Database
from app.store.models import Case, Channel, TelegramReport
from app.telegram import Submission, notify
from tests.stored import add_routed_case, database
from tests.test_telegram import ORIGIN, jpeg, publish_case

SECRET = "app-secret"  # noqa: S105 - test-only secret
VERIFY = "verify-me"


def event(**message: Any) -> dict[str, Any]:
    return {
        "sender": {"id": "7001"},
        "recipient": {"id": "1"},
        "timestamp": 1729650000000,
        "message": {"mid": "m_1"} | message,
    }


def payload(*events: dict[str, Any]) -> dict[str, Any]:
    return {"object": "page", "entry": [{"id": "1", "time": 0, "messaging": list(events)}]}


class FakeGraph:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=jpeg())
        assert request.headers["Authorization"] == "Bearer page-token"
        self.sent.append(json.loads(request.content))
        return httpx.Response(200, json={"message_id": "m_2"})

    def client(self) -> Messenger:
        return Messenger("page-token", httpx.Client(transport=httpx.MockTransport(self)))


def test_a_message_becomes_a_post_and_echoes_are_ignored() -> None:
    shared = {"type": "fallback", "payload": {"url": "https://www.facebook.com/reel/1"}}
    photo = {"type": "image", "payload": {"url": "https://cdn.example/a.jpg"}}
    posts = submissions(
        payload(
            event(text="बाढी आयो https://www.tiktok.com/@a/video/7 हेर्नुस्"),
            event(attachments=[shared]),
            event(text="hi", is_echo=True),
            event(attachments=[photo]),
        )
    )
    assert posts == [
        Submission(7001, 1729650000000, "बाढी आयो  हेर्नुस्", "https://www.tiktok.com/@a/video/7"),
        Submission(7001, 1729650000000, None, "https://www.facebook.com/reel/1"),
        Submission(7001, 1729650000000, None, None, [("https://cdn.example/a.jpg", 0)]),
    ]


def test_only_bodies_signed_with_the_app_secret_are_accepted() -> None:
    body = b'{"object":"page"}'
    good = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert signed(body, good, SECRET)
    assert not signed(body, good, "another-secret")
    assert not signed(body + b" ", good, SECRET)
    assert not signed(body, None, SECRET)


def webhook(db: Database, tmp_path: Path, graph: FakeGraph) -> TestClient:
    settings = Settings(media_root=tmp_path / "media", frontend_origin=ORIGIN)
    return TestClient(create_app(settings, db, graph.client(), VERIFY, SECRET))


def test_the_webhook_is_verified_with_the_token(tmp_path: Path) -> None:
    client = webhook(database(tmp_path), tmp_path, FakeGraph())
    query = {"hub.mode": "subscribe", "hub.challenge": "42"}
    assert client.get("/webhook", params=query | {"hub.verify_token": VERIFY}).text == "42"
    assert client.get("/webhook", params=query | {"hub.verify_token": "guess"}).status_code == 403


def test_a_signed_photo_becomes_a_messenger_case(tmp_path: Path) -> None:
    db, graph = database(tmp_path), FakeGraph()
    client = webhook(db, tmp_path, graph)
    photo = {"type": "image", "payload": {"url": "https://cdn.example/a.jpg"}}
    body = json.dumps(payload(event(text="रसुवामा बाढी", attachments=[photo]))).encode()
    sign = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

    assert client.post("/webhook", content=body).status_code == 403  # unsigned
    assert client.post("/webhook", content=body, headers={"X-Hub-Signature-256": sign}).is_success
    with db.session() as session:
        [case] = session.query(Case).all()
        assert (case.channel, case.text, len(case.media)) == (Channel.MESSENGER, "रसुवामा बाढी", 1)
    assert graph.sent[0]["recipient"] == {"id": "7001"}
    assert f"{ORIGIN}/check/{case.id}" in graph.sent[0]["message"]["text"]


def test_verdicts_go_back_on_the_channel_the_report_came_from(tmp_path: Path) -> None:
    db, graph = database(tmp_path), FakeGraph()
    for case_id, channel, chat in (("m1", Channel.MESSENGER, 7001), ("t1", Channel.TELEGRAM, 42)):
        add_routed_case(db, case_id)
        with db.session.begin() as session:
            session.get_one(Case, case_id).channel = channel
            session.add(TelegramReport(case_id=case_id, chat_id=chat, message_id=5))
        publish_case(db, case_id)
    assert notify(db, graph.client(), ORIGIN, Channel.MESSENGER) == 1
    assert [m["recipient"]["id"] for m in graph.sent] == ["7001"]


def test_long_verdicts_are_split_to_the_send_apis_limit() -> None:
    graph = FakeGraph()
    graph.client().send(7001, "क" * 4500)
    assert [len(m["message"]["text"]) for m in graph.sent] == [2000, 2000, 500]
