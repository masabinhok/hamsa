"""Messenger bot: `uv run python -m app.messenger` from backend/.

The same intake and verdict news as the Telegram bot (`app.telegram`), over a Facebook
Page. Meta delivers messages by webhook, so this serves one (port 8001) and needs a
public HTTPS address in front of it, e.g. `cloudflared tunnel --url localhost:8001`.
In development mode a Page's admins and testers can use it without app review.
"""

import hashlib
import hmac
import logging
import re
import sys
import threading
import time
from collections.abc import Iterable
from typing import Annotated, Any

import httpx
import uvicorn
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.api.main import MAX_FILE_BYTES, SUBMISSIONS_PER_MINUTE, RateLimiter
from app.config import Settings, get_settings
from app.store.cases import Database
from app.store.models import Channel
from app.telegram import ABOUT, ChatError, Submission, notify, receive

GRAPH = "https://graph.facebook.com/v21.0"
MAX_TEXT = 2000  # the Send API refuses longer messages
NOTIFY_S = 5
URL = re.compile(r"https?://\S+")
log = logging.getLogger("hamsa.messenger")


class Messenger:
    """The Send API and attachment downloads, as `app.telegram.Chat`."""

    def __init__(self, page_token: str, http: httpx.Client | None = None) -> None:
        self.http = http or httpx.Client(timeout=30, follow_redirects=True)
        self._auth = {"Authorization": f"Bearer {page_token}"}

    def download(self, file_id: str) -> bytes:
        """`file_id` is the attachment's URL on Meta's CDN."""
        with self.http.stream("GET", file_id) as response:
            if response.status_code != httpx.codes.OK.value:
                raise ChatError(response.status_code, "attachment download failed")
            data = b""
            for chunk in response.iter_bytes():
                data += chunk
                if len(data) > MAX_FILE_BYTES:
                    raise ChatError(413, "attachment over 100 MB")
        return data

    def greet(self, text: str) -> None:
        """The greeting a reader sees before writing to the page for the first time."""
        response = self.http.post(
            f"{GRAPH}/me/messenger_profile",
            headers=self._auth,
            json={"greeting": [{"locale": "default", "text": text}]},
        )
        if response.is_error:
            raise ChatError(response.status_code, response.text[:200])

    def send(self, chat_id: int, text: str, reply_to: int | None = None) -> None:
        for start in range(0, len(text), MAX_TEXT):
            response = self.http.post(
                f"{GRAPH}/me/messages",
                headers=self._auth,
                json={
                    "recipient": {"id": str(chat_id)},
                    "messaging_type": "RESPONSE",
                    "message": {"text": text[start : start + MAX_TEXT]},
                },
            )
            if response.is_error:
                raise ChatError(response.status_code, response.text[:200])


def submissions(payload: dict[str, Any]) -> list[Submission]:
    """One post per incoming message: its text, first link, and photos or videos."""
    posts: list[Submission] = []
    for entry in payload.get("entry", []):
        for event in entry.get("messaging", []):
            message: dict[str, Any] = event.get("message") or {}
            if not message or message.get("is_echo"):
                continue
            text = str(message.get("text") or "")
            url = next(iter(URL.findall(text)), None)
            files: list[tuple[str, int]] = []
            for attachment in message.get("attachments", []):
                content: dict[str, Any] = attachment.get("payload") or {}
                link = str(content.get("url") or "")
                if attachment.get("type") in ("image", "video") and link:
                    files.append((link, 0))  # the size is only known once downloaded
                elif link and url is None:
                    url = link  # a shared post arrives as a "share" or "fallback" link
            words = URL.sub("", text).strip() or None
            # The timestamp orders a chat's reports, as Telegram's message ids do.
            posts.append(
                Submission(int(event["sender"]["id"]), int(event["timestamp"]), words, url, files)
            )
    return posts


def signed(body: bytes, signature: str | None, app_secret: str) -> bool:
    """Meta signs every webhook body with the app secret; anything else is refused."""
    expected = "sha256=" + hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return signature is not None and hmac.compare_digest(expected, signature)


def create_app(
    settings: Settings, db: Database, messenger: Messenger, verify_token: str, app_secret: str
) -> FastAPI:
    limiter = RateLimiter(SUBMISSIONS_PER_MINUTE)
    app = FastAPI(title="Hamsa Messenger webhook")

    @app.get("/webhook", response_class=PlainTextResponse)
    def verify(
        mode: Annotated[str, Query(alias="hub.mode")],
        token: Annotated[str, Query(alias="hub.verify_token")],
        challenge: Annotated[str, Query(alias="hub.challenge")],
    ) -> str:
        if mode != "subscribe" or not hmac.compare_digest(token, verify_token):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "wrong verify token")
        return challenge

    @app.post("/webhook")
    async def incoming(
        request: Request,
        later: BackgroundTasks,
        signature: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
    ) -> dict[str, str]:
        body = await request.body()
        if not signed(body, signature, app_secret):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "bad signature")
        posts = submissions(await request.json())
        # Meta wants an answer within seconds; downloads can take longer.
        later.add_task(_receive, db, messenger, posts, settings, limiter)
        return {"status": "ok"}

    return app


def _receive(
    db: Database,
    messenger: Messenger,
    posts: Iterable[Submission],
    settings: Settings,
    limiter: RateLimiter,
) -> None:
    created = receive(
        db,
        messenger,
        posts,
        settings.media_root,
        settings.frontend_origin,
        limiter,
        Channel.MESSENGER,
    )
    if created:
        log.info("new cases: %s", ", ".join(created))


def _notify_forever(db: Database, messenger: Messenger, origin: str) -> None:
    while True:
        try:
            notify(db, messenger, origin, Channel.MESSENGER)
        except Exception:  # a bad poll must not stop verdicts reaching later senders
            log.exception("notify failed")
        time.sleep(NOTIFY_S)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # request URLs carry signed links
    settings = get_settings()
    page = settings.messenger_page_token
    app_secret = settings.messenger_app_secret
    verify = settings.messenger_verify_token
    if page is None or app_secret is None or verify is None:
        print(
            "set MESSENGER_PAGE_TOKEN, MESSENGER_APP_SECRET and MESSENGER_VERIFY_TOKEN in .env "
            "(docs/install.md)",
            file=sys.stderr,
        )
        return 1
    db = Database(settings.database_url)
    db.create_all()
    messenger = Messenger(page.get_secret_value())
    try:
        messenger.greet(ABOUT)
    except (ChatError, httpx.HTTPError) as error:  # a stale greeting must not stop intake
        log.warning("greeting not set: %s", type(error).__name__)
    threading.Thread(
        target=_notify_forever, args=(db, messenger, settings.frontend_origin), daemon=True
    ).start()
    app = create_app(
        settings, db, messenger, verify.get_secret_value(), app_secret.get_secret_value()
    )
    uvicorn.run(app, host="0.0.0.0", port=8001)  # noqa: S104
    return 0


if __name__ == "__main__":
    sys.exit(main())
