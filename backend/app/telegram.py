"""Telegram bot: `uv run python -m app.telegram` from backend/.

Anyone can forward a doubtful post to the bot. It becomes a case exactly like a web
submission, and the bot messages back when the fact-checkers publish. Long polling,
so the desk needs no public address.
"""

import logging
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import HttpUrl, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.main import (
    MAX_FILES,
    SUBMISSIONS_PER_MINUTE,
    RateLimiter,
    needs_media,
    published_verdict,
    sniff_suffix,
)
from app.config import get_settings
from app.store.cases import (
    Database,
    StoredMedia,
    add_sent_media,
    answered_by,
    create_case,
    new_case_id,
    save_media,
)
from app.store.models import Case, CaseEvent, CaseStatus, Channel, TelegramReport

API = "https://api.telegram.org"
POLL_S = 25  # long-poll timeout; getUpdates returns at once when a message arrives
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # the Bot API will not serve larger files to a bot
log = logging.getLogger("hamsa.telegram")

# The marker repeats the desk's verdict colours, so a verdict reads at a glance in a chat list.
LABELS = {
    "false": "🔴 गलत · False",
    "misleading": "🟠 भ्रामक · Misleading",
    "true": "🟢 सत्य · True",
    "unverifiable": "⚪ पुष्टि हुन नसकेको · Unverifiable",
}

HELP = (
    "नमस्ते! बाढी, पहिरो, भूकम्प वा अरू विपद्‌बारे शंकास्पद पोस्ट यहाँ फर्वार्ड गर्नुहोस्, "
    "वा यसको लिंक, फोटो वा भिडियो पठाउनुहोस्। तथ्य जाँचकर्ताहरूले हेरेर निर्णय प्रकाशित "
    "गरेपछि यहीँ खबर गर्छौं।\n\n"
    "Hello! Forward a doubtful post about a flood, landslide, earthquake or other disaster "
    "in Nepal, or send its link, photo or video. Fact-checkers look at every post, and we "
    "message you here when they publish a verdict."
)
# The bot's profile: the description greets a reader before they press Start.
ABOUT = "विपद्‌बारे शंकास्पद पोस्ट पठाउनुहोस्। Send a doubtful disaster post; fact-checkers reply."
# Every command answers with HELP; listing one gives readers the menu button.
COMMANDS = [{"command": "help", "description": "कसरी पठाउने · How to send a post"}]
NOTHING = (
    "पोस्टको लिंक, लेखिएको कुरा, फोटो वा भिडियो पठाउनुहोस्।\n"
    "Send the post's link, its text, or its photo or video."
)
TOO_MANY_FILES = f"बढीमा {MAX_FILES} वटा फाइल पठाउनुहोस्।\nSend at most {MAX_FILES} files."
TOO_BIG = (
    "फाइल २० MB भन्दा ठूलो छ, Telegram ले बोटलाई दिँदैन। पोस्टको लिंक पठाउनुहोस्।\n"
    "The file is over 20 MB, which Telegram does not pass to bots. Send the post's link instead."
)
UNSUPPORTED = (
    "फोटो (JPEG, PNG, WebP) वा भिडियो (MP4, WebM) मात्र जाँच्न सकिन्छ।\n"
    "Only photos (JPEG, PNG, WebP) and videos (MP4, WebM) can be checked."
)
NOT_RECEIVED = (
    "फाइल लिन सकिएन। फेरि पठाउनुहोस्।\nThe file could not be received. Please send it again."
)
SLOW_DOWN = "धेरै पठाइयो। एक मिनेट पर्खनुहोस्।\nToo many submissions. Please wait a minute."
MERGED = (
    "यो पोस्ट पहिले नै कसैले पठाइसक्नुभएको छ। त्यही रिपोर्टमा जाँच हुँदैछ, निर्णय आएपछि खबर गर्छौं।\n"
    "Someone already sent this post. It is being checked under that report; we will tell you "
    "the verdict."
)
CHECKING_AGAIN = (
    "फाइल पायौं। तपाईंको रिपोर्ट फेरि जाँच हुँदैछ।\nGot the file. Your report is being checked again."
)
REJECTED = (
    "निर्णय प्रकाशित भएन: पोस्टमा जाँच्न मिल्ने तथ्यगत दाबी छैन।\n"
    "No verdict was published: the post makes no factual claim that can be checked."
)
ASK_FOR_MEDIA = (
    "हामी लिंक खोल्न सकेनौं (पोस्ट निजी वा हटाइएको हुन सक्छ)। फोटो वा भिडियो यहीँ पठाउनुहोस्।\n"
    "We could not open the link (the post may be private or deleted). Send the photo or "
    "video here, and we will check it under the same report."
)


class ChatError(Exception):
    """A chat platform's refusal (Telegram, Messenger). Never carries the request URL,
    which may hold the token."""

    def __init__(self, status: int, description: str) -> None:
        super().__init__(f"{status}: {description}")
        self.status = status


class Telegram:
    """The few Bot API methods Hamsa uses."""

    def __init__(self, token: str, http: httpx.Client | None = None) -> None:
        self.http = http or httpx.Client(timeout=POLL_S + 10)
        self._methods = f"{API}/bot{token}"
        self._files = f"{API}/file/bot{token}"

    def call(self, method: str, **params: Any) -> Any:
        response = self.http.post(f"{self._methods}/{method}", json=params)
        try:
            body: dict[str, Any] = response.json()
        except ValueError:
            body = {}
        if not body.get("ok"):
            raise ChatError(response.status_code, str(body.get("description", "no body")))
        return body["result"]

    def download(self, file_id: str) -> bytes:
        found: dict[str, Any] = self.call("getFile", file_id=file_id)
        response = self.http.get(f"{self._files}/{found['file_path']}")
        if response.status_code != httpx.codes.OK.value:
            raise ChatError(response.status_code, "file download failed")
        return response.content

    def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        params: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "link_preview_options": {"is_disabled": True},
        }
        if reply_to is not None:
            params["reply_parameters"] = {
                "message_id": reply_to,
                "allow_sending_without_reply": True,
            }
        self.call("sendMessage", **params)


class Chat(Protocol):
    """What intake and verdict news need from a chat platform (Telegram, Messenger)."""

    def download(self, file_id: str) -> bytes: ...

    def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None: ...


@dataclass
class Submission:
    """One post: a single message, or every message of an album."""

    chat_id: int
    message_id: int
    text: str | None = None
    url: str | None = None
    files: list[tuple[str, int]] = field(default_factory=list[tuple[str, int]])  # id, bytes
    command: str | None = None


def _entity_text(text: str, entity: dict[str, Any]) -> str:
    # Telegram counts offsets in UTF-16 code units; emoji take two.
    units = text.encode("utf-16-le")
    start, length = int(entity["offset"]) * 2, int(entity["length"]) * 2
    return units[start : start + length].decode("utf-16-le")


def _without_links(text: str, entities: Iterable[dict[str, Any]]) -> str:
    for link in [_entity_text(text, e) for e in entities if e.get("type") == "url"]:
        text = text.replace(link, "")
    return text


def _first_url(text: str, entities: Iterable[dict[str, Any]]) -> str | None:
    for entity in entities:
        if entity.get("type") == "url":
            candidate = _entity_text(text, entity)
        elif entity.get("type") == "text_link":
            candidate = str(entity.get("url", ""))
        else:
            continue
        if not candidate.startswith(("http://", "https://")):
            candidate = f"https://{candidate}"
        try:
            return str(TypeAdapter(HttpUrl).validate_python(candidate))
        except ValidationError:
            continue
    return None


def _files(message: dict[str, Any]) -> list[tuple[str, int]]:
    if photo := message.get("photo"):
        largest: dict[str, Any] = photo[-1]  # sizes come smallest first
        return [(largest["file_id"], int(largest.get("file_size", 0)))]
    for kind in ("video", "animation"):
        if found := message.get(kind):
            return [(found["file_id"], int(found.get("file_size", 0)))]
    document: dict[str, Any] | None = message.get("document")
    if document and str(document.get("mime_type", "")).startswith(("image/", "video/")):
        return [(document["file_id"], int(document.get("file_size", 0)))]
    return []


def submissions(updates: Iterable[dict[str, Any]]) -> list[Submission]:
    """Private messages as posts to check; the parts of an album become one post.

    shortcut: an album split across two getUpdates batches becomes two cases; buffer
    albums for a second if that shows up in practice.
    """
    found: list[Submission] = []
    albums: dict[tuple[int, str], Submission] = {}
    for update in updates:
        message: dict[str, Any] | None = update.get("message")
        if not message or message.get("chat", {}).get("type") != "private":
            continue  # groups and channels could flood the desk; only direct messages count
        chat_id, message_id = int(message["chat"]["id"]), int(message["message_id"])
        text: str = message.get("text") or message.get("caption") or ""
        entities: list[dict[str, Any]] = (
            message.get("entities") or message.get("caption_entities") or []
        )

        group = message.get("media_group_id")
        if group is not None and (chat_id, group) in albums:
            post = albums[(chat_id, group)]
        else:
            post = Submission(chat_id, message_id)
            found.append(post)
            if group is not None:
                albums[(chat_id, group)] = post

        if text.startswith("/"):
            post.command = text.split()[0].split("@")[0]
            continue
        if text.strip():
            post.url = post.url or _first_url(text, entities)
            # A bare link is no claim; leaving the text empty lets the post's caption be one.
            if _without_links(text, entities).strip():
                post.text = text.strip()
        post.files.extend(_files(message))
    return found


def _reply(telegram: Chat, post: Submission, text: str) -> None:
    try:
        telegram.send(post.chat_id, text, reply_to=post.message_id)
    except (ChatError, httpx.HTTPError) as error:
        log.warning("reply to a message failed: %s", type(error).__name__)


def receive(
    db: Database,
    telegram: Chat,
    posts: Iterable[Submission],
    media_root: Path,
    origin: str,
    limiter: RateLimiter,
    channel: Channel = Channel.TELEGRAM,
) -> list[str]:
    """Turn each post into a case and acknowledge it. Returns the new case ids."""
    created: list[str] = []
    for post in posts:
        if post.command is not None:
            _reply(telegram, post, HELP)
            continue
        if not (post.text or post.url or post.files):
            _reply(telegram, post, NOTHING)
            continue
        if len(post.files) > MAX_FILES:
            _reply(telegram, post, TOO_MANY_FILES)
            continue
        if any(size > MAX_DOWNLOAD_BYTES for _, size in post.files):
            _reply(telegram, post, TOO_BIG)
            continue
        if not limiter.allow(str(post.chat_id), time.monotonic()):
            _reply(telegram, post, SLOW_DOWN)
            continue

        waiting = _waiting_for_media(db, post) if post.files and not post.url else None
        case_id = waiting or new_case_id()
        stored: list[StoredMedia] = []
        problem: str | None = None
        for file_id, _ in post.files:
            try:
                data = telegram.download(file_id)
            except (ChatError, httpx.HTTPError) as error:
                log.warning("file download failed: %s", type(error).__name__)
                problem = NOT_RECEIVED
                break
            suffix = sniff_suffix(data)
            if suffix is None:
                problem = UNSUPPORTED
                break
            stored.append(save_media(media_root, case_id, data, suffix))
        if problem is not None:
            _reply(telegram, post, problem)
            continue

        if waiting is not None:
            with db.session.begin() as session:
                add_sent_media(session, session.get_one(Case, waiting), stored)
            _reply(telegram, post, f"{CHECKING_AGAIN}\n\n{status_link(origin, waiting)}")
            continue

        with db.session.begin() as session:
            create_case(session, case_id, channel, post.text, post.url, stored)
            session.add(
                TelegramReport(case_id=case_id, chat_id=post.chat_id, message_id=post.message_id)
            )
        created.append(case_id)
        _reply(
            telegram,
            post,
            f"प्राप्त भयो। रिपोर्ट नं. {case_id}। तथ्य जाँचकर्ताहरूले निर्णय प्रकाशित गरेपछि "
            f"यहीँ खबर गर्छौं।\nReceived: report {case_id}. We will message you here when the "
            f"fact-checkers publish a verdict.\n\n{status_link(origin, case_id)}",
        )
    return created


def _waiting_for_media(db: Database, post: Submission) -> str | None:
    """This chat's newest report the bot asked a file for, while it still waits for one:
    the file belongs to that report, not to a new one beside it."""
    with db.session() as session:
        reports = session.scalars(
            select(TelegramReport)
            .where(TelegramReport.chat_id == post.chat_id, TelegramReport.asked_for_media)
            .order_by(TelegramReport.message_id.desc())
        )
        for report in reports:
            case = session.get_one(Case, report.case_id)
            if case.status is CaseStatus.ROUTED and needs_media(case):
                return case.id
    return None


def status_link(origin: str, case_id: str) -> str:
    return f"{origin.rstrip('/')}/check/{case_id}"


def _latest_event(session: Session, case_id: str, status: CaseStatus) -> CaseEvent | None:
    query = (
        select(CaseEvent)
        .where(CaseEvent.case_id == case_id, CaseEvent.to_status == status.value)
        .order_by(CaseEvent.id.desc())
        .limit(1)
    )
    return session.scalar(query)


def news_for(session: Session, case: Case, origin: str) -> tuple[int, str] | None:
    """The newest thing the submitter should hear, with the event id it answers."""
    checked = answered_by(session, case)
    if checked.status is CaseStatus.PUBLISHED:
        event = _latest_event(session, checked.id, CaseStatus.PUBLISHED)
        verdict = published_verdict(checked)
        if event is None or verdict is None:
            return None
        lines = [LABELS[verdict.label.value], "", verdict.rationale_ne, "", verdict.rationale_en]
        if verdict.sources:
            lines += ["", "स्रोत · Sources:"]
            lines += [f"• {source.name}: {source.url}" for source in verdict.sources[:4]]
        lines += ["", status_link(origin, checked.id)]
        return event.id, "\n".join(lines)
    if checked.status is CaseStatus.REJECTED:
        event = _latest_event(session, checked.id, CaseStatus.REJECTED)
        return (event.id, REJECTED) if event else None
    if case.status is CaseStatus.MERGED:
        event = _latest_event(session, case.id, CaseStatus.MERGED)
        return (event.id, MERGED) if event else None
    return None


def notify(db: Database, telegram: Chat, origin: str, channel: Channel = Channel.TELEGRAM) -> int:
    """Message every submitter on this channel whose report has news. Returns how many."""
    sent = 0
    with db.session.begin() as session:
        # shortcut: scans every report each poll; add a done flag once there are thousands.
        reports = select(TelegramReport).join(Case).where(Case.channel == channel)
        for report in session.scalars(reports):
            case = session.get_one(Case, report.case_id)
            messages: list[str] = []
            if not report.asked_for_media and needs_media(case):
                messages.append(ASK_FOR_MEDIA)
            news = news_for(session, case, origin)
            if news and news[0] > report.told_event:
                messages.append(news[1])
            if not messages:
                continue
            try:
                for text in messages:
                    telegram.send(report.chat_id, text, reply_to=report.message_id)
                    sent += 1
            except ChatError as error:
                if error.status != httpx.codes.FORBIDDEN.value:  # the user blocked the bot
                    log.warning("case %s: message not sent (%s)", case.id, error.status)
                    continue
            except httpx.HTTPError as error:
                log.warning("case %s: message not sent (%s)", case.id, type(error).__name__)
                continue
            report.asked_for_media = report.asked_for_media or needs_media(case)
            if news:
                report.told_event = max(report.told_event, news[0])
    return sent


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # httpx logs every request URL at INFO, and Bot API URLs contain the token.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = get_settings()
    if settings.telegram_bot_token is None:
        print("set TELEGRAM_BOT_TOKEN in .env (create a bot with @BotFather)", file=sys.stderr)
        return 1
    db = Database(settings.database_url)
    db.create_all()
    telegram = Telegram(settings.telegram_bot_token.get_secret_value())
    limiter = RateLimiter(SUBMISSIONS_PER_MINUTE)
    try:
        me: dict[str, Any] = telegram.call("getMe")
    except (ChatError, httpx.HTTPError) as error:
        detail = error if isinstance(error, ChatError) else type(error).__name__
        print(f"could not reach the bot: {detail}", file=sys.stderr)
        return 1
    log.info("bot @%s ready", me.get("username"))
    try:
        telegram.call("setMyDescription", description=HELP)
        telegram.call("setMyShortDescription", short_description=ABOUT)
        telegram.call("setMyCommands", commands=COMMANDS)
    except (ChatError, httpx.HTTPError) as error:  # a stale profile must not stop intake
        log.warning("profile not set: %s", type(error).__name__)

    offset: int | None = None
    try:
        while True:
            params: dict[str, Any] = {"timeout": POLL_S, "allowed_updates": ["message"]}
            if offset is not None:
                params["offset"] = offset
            try:
                updates: list[dict[str, Any]] = telegram.call("getUpdates", **params)
            except (ChatError, httpx.HTTPError) as error:
                log.warning("getUpdates failed (%s); retrying", type(error).__name__)
                time.sleep(5)
                updates = []
            if updates:
                offset = int(updates[-1]["update_id"]) + 1
                created = receive(
                    db,
                    telegram,
                    submissions(updates),
                    settings.media_root,
                    settings.frontend_origin,
                    limiter,
                )
                if created:
                    log.info("new cases: %s", ", ".join(created))
            notify(db, telegram, settings.frontend_origin)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
