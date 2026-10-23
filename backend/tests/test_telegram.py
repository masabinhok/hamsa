import io
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.api.main import RateLimiter
from app.pipeline.contracts import Route, RouteDecision, VerdictLabel
from app.store.cases import Database, claim_job, complete_job, create_case, publish, reopen
from app.store.models import Case, CaseStatus, Channel, TelegramReport
from app.telegram import (
    HELP,
    MERGED,
    TOO_BIG,
    UNSUPPORTED,
    ChatError,
    Submission,
    Telegram,
    notify,
    receive,
    submissions,
)
from tests.factories import cite, outputs, passage, verdict
from tests.images import photo
from tests.stored import add_routed_case, database, routed_result

TOKEN = "123:secret"  # noqa: S105 - test-only token
ORIGIN = "https://hamsa.example"


def jpeg() -> bytes:
    buffer = io.BytesIO()
    photo(1).save(buffer, "JPEG")
    return buffer.getvalue()


class FakeBotApi:
    """The Bot API's getFile, file download and sendMessage, recording what was sent."""

    def __init__(self, files: dict[str, bytes] | None = None, send_status: int = 200) -> None:
        self.files = files or {}
        self.send_status = send_status
        self.sent: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith(f"/file/bot{TOKEN}/"):
            name = path.rsplit("/", 1)[-1]
            return httpx.Response(200, content=self.files[name])
        method = path.rsplit("/", 1)[-1]
        params = json.loads(request.content or b"{}")
        if method == "getFile":
            return httpx.Response(
                200, json={"ok": True, "result": {"file_path": f"photos/{params['file_id']}"}}
            )
        if method == "sendMessage":
            if self.send_status != 200:
                return httpx.Response(
                    self.send_status, json={"ok": False, "description": "Forbidden"}
                )
            self.sent.append(params)
            return httpx.Response(200, json={"ok": True, "result": {}})
        return httpx.Response(404, json={"ok": False, "description": "Not Found"})

    def client(self) -> Telegram:
        return Telegram(TOKEN, httpx.Client(transport=httpx.MockTransport(self)))


def message(
    message_id: int, chat_id: int = 42, chat_type: str = "private", **fields: Any
) -> dict[str, Any]:
    chat = {"id": chat_id, "type": chat_type}
    return {"update_id": message_id, "message": {"message_id": message_id, "chat": chat} | fields}


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return database(tmp_path)


def run_receive(
    db: Database, api: FakeBotApi, posts: list[Submission], tmp_path: Path
) -> list[str]:
    return receive(db, api.client(), posts, tmp_path / "media", ORIGIN, RateLimiter(10))


# reading messages


def test_caption_link_and_largest_photo_become_one_post() -> None:
    caption = "😱 रसुवामा बाढी https://www.facebook.com/reel/123"
    url_start = len(caption.split("https")[0].encode("utf-16-le")) // 2
    [post] = submissions(
        [
            message(
                7,
                caption=caption,
                caption_entities=[{"type": "url", "offset": url_start, "length": 33}],
                photo=[{"file_id": "small", "file_size": 10}, {"file_id": "big", "file_size": 99}],
            )
        ]
    )
    assert post.text == caption
    assert post.url == "https://www.facebook.com/reel/123"
    assert post.files == [("big", 99)]


def test_album_parts_are_one_post_and_groups_are_ignored() -> None:
    posts = submissions(
        [
            message(1, media_group_id="a", caption="बाढी", photo=[{"file_id": "p1"}]),
            message(2, media_group_id="a", photo=[{"file_id": "p2"}]),
            message(3, chat_id=-100, chat_type="group", text="from a group"),
        ]
    )
    assert [(p.message_id, p.text, [f for f, _ in p.files]) for p in posts] == [
        (1, "बाढी", ["p1", "p2"])
    ]


def test_hidden_links_and_commands_are_read() -> None:
    linked, start = submissions(
        [
            message(
                1,
                text="this video",
                entities=[
                    {
                        "type": "text_link",
                        "offset": 0,
                        "length": 4,
                        "url": "https://x.com/a/status/1",
                    }
                ],
            ),
            message(2, text="/start@HamsaBot"),
        ]
    )
    assert linked.url == "https://x.com/a/status/1"
    assert start.command == "/start"


def test_a_bare_link_leaves_the_text_for_the_posts_caption() -> None:
    link = "https://www.facebook.com/share/v/1abc/"
    [post] = submissions(
        [message(1, text=f" {link} ", entities=[{"type": "url", "offset": 1, "length": len(link)}])]
    )
    assert (post.text, post.url) == (None, link)


# creating cases


def test_photo_becomes_a_telegram_case_and_is_acknowledged(db: Database, tmp_path: Path) -> None:
    api = FakeBotApi(files={"big": jpeg()})
    [case_id] = run_receive(
        db, api, [Submission(42, 7, text="रसुवामा बाढी", files=[("big", 10)])], tmp_path
    )

    with db.session() as session:
        case = session.get_one(Case, case_id)
        report = session.get_one(TelegramReport, case_id)
        assert case.channel is Channel.TELEGRAM
        assert case.text == "रसुवामा बाढी"
        assert [m.filename.endswith(".jpg") for m in case.media] == [True]
        assert (report.chat_id, report.message_id) == (42, 7)
    [ack] = api.sent
    assert ack["chat_id"] == 42
    assert ack["reply_parameters"]["message_id"] == 7
    assert f"{ORIGIN}/check/{case_id}" in ack["text"]


def test_a_link_alone_is_enough(db: Database, tmp_path: Path) -> None:
    api = FakeBotApi()
    [case_id] = run_receive(
        db, api, [Submission(42, 7, url="https://www.tiktok.com/@a/video/1")], tmp_path
    )
    with db.session() as session:
        assert session.get_one(Case, case_id).source_url == "https://www.tiktok.com/@a/video/1"


@pytest.mark.parametrize(
    ("post", "files", "reply"),
    [
        (Submission(42, 1, command="/start"), {}, HELP),
        (Submission(42, 1, files=[("huge", 25 * 1024 * 1024)]), {}, TOO_BIG),
        (Submission(42, 1, files=[("doc", 5)]), {"doc": b"%PDF-1.7 not media"}, UNSUPPORTED),
    ],
)
def test_posts_that_cannot_be_checked_get_a_reason_and_no_case(
    db: Database, tmp_path: Path, post: Submission, files: dict[str, bytes], reply: str
) -> None:
    api = FakeBotApi(files=files)
    assert run_receive(db, api, [post], tmp_path) == []
    assert [sent["text"] for sent in api.sent] == [reply]
    with db.session() as session:
        assert session.scalars(select(Case)).all() == []


def test_a_chat_sending_too_fast_is_slowed(db: Database, tmp_path: Path) -> None:
    api = FakeBotApi()
    posts = [Submission(42, n, text=f"post {n}") for n in range(3)]
    created = receive(db, api.client(), posts, tmp_path / "media", ORIGIN, RateLimiter(2))
    assert len(created) == 2
    assert "wait a minute" in api.sent[-1]["text"]


# telling the submitter


def telegram_case(db: Database, case_id: str, chat_id: int = 42) -> None:
    """A routed case that came in through the bot."""
    result = routed_result(
        outputs(
            passages=[passage("p1", "Nepal Factcheck", source_kind="fact_check")],
            verdict=verdict("false", citations=[cite("p1")]),
        )
    )
    add_routed_case(db, case_id, result)
    with db.session.begin() as session:
        session.add(TelegramReport(case_id=case_id, chat_id=chat_id, message_id=5))
        session.get_one(Case, case_id).channel = Channel.TELEGRAM


def publish_case(db: Database, case_id: str, rationale_en: str = "It is old footage.") -> None:
    with db.session.begin() as session:
        case = session.get_one(Case, case_id)
        publish(session, case, "Sita", VerdictLabel.FALSE, rationale_en, "पुरानो भिडियो हो।", None)


def test_published_verdict_is_sent_once(db: Database) -> None:
    api = FakeBotApi()
    telegram_case(db, "c1")
    assert notify(db, api.client(), ORIGIN) == 0  # still on the desk

    publish_case(db, "c1")
    assert notify(db, api.client(), ORIGIN) == 1
    assert notify(db, api.client(), ORIGIN) == 0
    [sent] = api.sent
    assert sent["chat_id"] == 42
    assert sent["text"].startswith("गलत · False")
    assert "पुरानो भिडियो हो।" in sent["text"]
    assert "Nepal Factcheck: https://example.org/p1" in sent["text"]
    assert sent["text"].endswith(f"{ORIGIN}/check/c1")


def test_a_corrected_verdict_is_sent_again(db: Database) -> None:
    api = FakeBotApi()
    telegram_case(db, "c1")
    publish_case(db, "c1")
    notify(db, api.client(), ORIGIN)
    with db.session.begin() as session:
        reopen(session, session.get_one(Case, "c1"), "Sita", "wrong place named")
    assert notify(db, api.client(), ORIGIN) == 0  # reopened, nothing new to say yet

    publish_case(db, "c1", rationale_en="It is old footage from Kullu.")
    assert notify(db, api.client(), ORIGIN) == 1
    assert "Kullu" in api.sent[-1]["text"]


def test_a_merged_report_hears_the_earlier_reports_verdict(db: Database) -> None:
    api = FakeBotApi()
    add_routed_case(db, "first")
    with db.session.begin() as session:
        create_case(session, "second", Channel.TELEGRAM, "same post", None, [])
        session.add(TelegramReport(case_id="second", chat_id=42, message_id=9))
        session.get_one(Case, "second").channel = Channel.TELEGRAM
    merge = RouteDecision(route=Route.MERGE, reasons=["same media"], merge_into="first")
    with db.session.begin() as session:
        claimed = claim_job(session)
        assert claimed is not None
        second = session.get_one(Case, "second")
        complete_job(session, claimed[0], second, outputs(), merge, {})

    assert notify(db, api.client(), ORIGIN) == 1
    assert api.sent[-1]["text"] == MERGED
    publish_case(db, "first")
    assert notify(db, api.client(), ORIGIN) == 1
    assert api.sent[-1]["text"].endswith(f"{ORIGIN}/check/first")


def test_an_unopenable_link_asks_for_the_file_once(db: Database) -> None:
    api = FakeBotApi()
    add_routed_case(db, "c1")
    with db.session.begin() as session:
        session.get_one(Case, "c1").source_url = "https://www.facebook.com/reel/1"
        session.add(TelegramReport(case_id="c1", chat_id=42, message_id=5))
        session.get_one(Case, "c1").channel = Channel.TELEGRAM
    assert notify(db, api.client(), ORIGIN) == 1
    assert notify(db, api.client(), ORIGIN) == 0
    assert "Send the photo or video here" in api.sent[0]["text"]


def test_the_file_sent_after_the_ask_joins_the_same_report(db: Database, tmp_path: Path) -> None:
    api = FakeBotApi(files={"big": jpeg()})
    add_routed_case(db, "c1")
    with db.session.begin() as session:
        session.get_one(Case, "c1").source_url = "https://www.facebook.com/reel/1"
        session.add(TelegramReport(case_id="c1", chat_id=42, message_id=5))
        session.get_one(Case, "c1").channel = Channel.TELEGRAM
    notify(db, api.client(), ORIGIN)  # asks for the file

    created = run_receive(db, api, [Submission(42, 9, files=[("big", 10)])], tmp_path)
    assert created == []  # no second report beside the first
    with db.session() as session:
        case = session.get_one(Case, "c1")
        assert (case.status, len(case.media)) == (CaseStatus.RECEIVED, 1)
    assert "checked again" in api.sent[-1]["text"]
    # Once it has its file, the next photo is a new report again; so is another chat's.
    assert len(run_receive(db, api, [Submission(42, 10, files=[("big", 10)])], tmp_path)) == 1
    assert len(run_receive(db, api, [Submission(7, 11, files=[("big", 10)])], tmp_path)) == 1


def test_a_user_who_blocked_the_bot_is_not_retried(db: Database) -> None:
    api = FakeBotApi(send_status=403)
    telegram_case(db, "c1")
    publish_case(db, "c1")
    notify(db, api.client(), ORIGIN)
    with db.session() as session:
        assert session.get_one(TelegramReport, "c1").told_event > 0
        assert session.get_one(Case, "c1").status is CaseStatus.PUBLISHED


def test_errors_never_carry_the_token() -> None:
    api = FakeBotApi()
    with pytest.raises(ChatError) as raised:
        api.client().call("noSuchMethod")
    assert TOKEN not in str(raised.value)
