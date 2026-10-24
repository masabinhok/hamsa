"""HTTP API: `uv run uvicorn --factory app.api.main:default_app` from backend/.

Public: submit a post, check its status, read published verdicts.
Desk (checker token): the queue, full case detail with model drafts, and decisions.
"""

import secrets
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import httpx
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import HttpUrl, SecretStr, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    Action,
    CaseCreated,
    DecisionRequest,
    DeskCase,
    DeskEvent,
    DeskSummary,
    EarlierFootage,
    PublicCase,
    PublicClaim,
    PublicStep,
    PublishedVerdict,
    Source,
    TranslateRequest,
    TranslateResponse,
)
from app.checkers import signed_in
from app.config import REPO_ROOT, get_settings
from app.ingest.download import is_platform_url
from app.llm.groq import GroqClient, ReasonerUnavailable
from app.llm.ollama import OllamaClient
from app.llm.structured import StructuredOutputError
from app.pipeline.contracts import Route, VerdictLabel
from app.pipeline.verdict import Reasoner, translate
from app.store.cases import (
    Database,
    DecisionError,
    StoredMedia,
    add_sent_media,
    answered_by,
    create_case,
    desk_queue,
    new_case_id,
    outputs_from_json,
    publish,
    published,
    reject,
    reopen,
    save_media,
)
from app.store.models import Case, CaseEvent, CaseStatus, Channel, Checker

SUBMISSIONS_PER_MINUTE = 10  # per client IP; a fact-check desk is not a bulk API
# Checker codes are unguessable, but the operator picks DESK_TOKEN and may pick a weak one.
FAILED_SIGN_INS_PER_MINUTE = 10
MAX_FILES = 4
MAX_FILE_BYTES = 100 * 1024 * 1024
MAX_TEXT_CHARS = 5000

# Recognised by content, never by the client's file name or declared type.
SIGNATURES: list[tuple[int, bytes, str]] = [
    (0, b"\xff\xd8\xff", ".jpg"),
    (0, b"\x89PNG\r\n\x1a\n", ".png"),
    (8, b"WEBP", ".webp"),
    (4, b"ftyp", ".mp4"),  # also covers .mov and .m4v containers
    (0, b"\x1a\x45\xdf\xa3", ".webm"),  # also covers .mkv
]


def sniff_suffix(data: bytes) -> str | None:
    for offset, magic, suffix in SIGNATURES:
        if data[offset : offset + len(magic)] == magic:
            return suffix
    return None


def get_session(request: Request) -> Iterator[Session]:
    db: Database = request.app.state.db
    with db.session.begin() as session:
        yield session


def require_checker(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    """The signed-in checker's name, or None for the operator's DESK_TOKEN."""
    token: SecretStr | None = request.app.state.desk_token
    if token is None and session.scalar(select(Checker.id).limit(1)) is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "desk disabled: add a checker (python -m app.checkers add NAME) or set DESK_TOKEN",
        )
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access code required")
    failures: RateLimiter = request.app.state.failed_sign_ins
    client, now = client_ip(request), time.monotonic()
    # Checked before the code, so a blocked guesser learns nothing even from a right guess.
    if failures.exceeded(client, now):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "too many wrong codes, wait a minute"
        )
    code = authorization.removeprefix("Bearer ")
    if token is not None and secrets.compare_digest(code, token.get_secret_value()):
        return None
    if name := signed_in(session, code):
        return name
    failures.allow(client, now)  # records the failure
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "access code not recognised")


class RateLimiter:
    """In-memory sliding window per client IP. One API process, so memory is enough."""

    def __init__(self, limit: int, window_s: float = 60.0) -> None:
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def exceeded(self, key: str, now: float) -> bool:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_s:
            hits.popleft()
        return len(hits) >= self.limit

    def allow(self, key: str, now: float) -> bool:
        if self.exceeded(key, now):
            return False
        self._hits[key].append(now)
        return True


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit_submissions(request: Request) -> None:
    limiter: RateLimiter = request.app.state.limiter
    if not limiter.allow(client_ip(request), time.monotonic()):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "too many submissions, wait a minute"
        )


DbSession = Annotated[Session, Depends(get_session)]
public = APIRouter()
desk = APIRouter(prefix="/desk", dependencies=[Depends(require_checker)])


def get_case(session: Session, case_id: str) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such case")
    return case


@public.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@public.post(
    "/cases", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(limit_submissions)]
)
async def submit(
    request: Request,
    session: DbSession,
    text: Annotated[str | None, Form(max_length=MAX_TEXT_CHARS)] = None,
    url: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> CaseCreated:
    uploads = files or []
    text = text.strip() if text and text.strip() else None
    if url:
        try:
            url = str(TypeAdapter(HttpUrl).validate_python(url))
        except ValidationError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid url") from error
        if not is_platform_url(url):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "only Facebook, TikTok, X, YouTube or Instagram post links",
            )
    if not (text or uploads or url):  # a link alone is fetched by the worker (ADR 0010)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "send text, a link, or media")
    if len(uploads) > MAX_FILES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"at most {MAX_FILES} files")

    case_id = new_case_id()
    stored = await save_uploads(request, case_id, uploads)
    create_case(session, case_id, Channel.WEB, text, url, stored)
    return CaseCreated(id=case_id, status=CaseStatus.RECEIVED)


@public.post("/cases/{case_id}/media", dependencies=[Depends(limit_submissions)])
async def send_media(
    request: Request,
    session: DbSession,
    case_id: str,
    files: Annotated[list[UploadFile], File()],
) -> PublicCase:
    """The file behind a link the worker could not open, sent from the report page."""
    case = get_case(session, case_id)
    if case.status is not CaseStatus.ROUTED or not needs_media(case):
        raise HTTPException(status.HTTP_409_CONFLICT, "this report is not waiting for media")
    if not files or len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"send 1 to {MAX_FILES} files")
    add_sent_media(session, case, await save_uploads(request, case_id, files))
    session.flush()
    return public_view(session, case)


@public.get("/cases/{case_id}")
def public_case(session: DbSession, case_id: str) -> PublicCase:
    return public_view(session, get_case(session, case_id))


@public.get("/cases/{case_id}/media/{name}")
def public_media(request: Request, session: DbSession, case_id: str, name: str) -> FileResponse:
    """A post's upload, once a checker has published: unreviewed uploads could be anything."""
    case = get_case(session, case_id)
    if case.status is not CaseStatus.PUBLISHED or name not in {m.filename for m in case.media}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such media")
    media_root: Path = request.app.state.media_root
    return FileResponse(media_root / case_id / name)


@public.get("/verdicts")
def verdicts(session: DbSession) -> list[PublicCase]:
    return [public_view(session, c) for c in published(session)]


@desk.get("/me")
def me(who: Annotated[str | None, Depends(require_checker)]) -> dict[str, str | None]:
    """Who this access code belongs to; None means the operator token, which names nobody."""
    return {"name": who}


@desk.get("/queue")
def queue(session: DbSession, route: Route | None = None) -> list[DeskSummary]:
    return [summary(c) for c in desk_queue(session, route)]


@desk.get("/cases/{case_id}")
def desk_case(session: DbSession, case_id: str) -> DeskCase:
    return detail(get_case(session, case_id))


@desk.get("/cases/{case_id}/media/{name}")
def media(request: Request, session: DbSession, case_id: str, name: str) -> FileResponse:
    case = get_case(session, case_id)
    if name not in {m.filename for m in case.media}:  # also blocks path traversal
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such media")
    media_root: Path = request.app.state.media_root
    return FileResponse(media_root / case_id / name)


@desk.get("/cases/{case_id}/archive/{archive_id}")
def archive_media(
    request: Request, session: DbSession, case_id: str, archive_id: str
) -> FileResponse:
    """The archive original behind one of this case's matches, for the side-by-side view."""
    case = get_case(session, case_id)
    matched = outputs_from_json(case.outputs).media_match if case.outputs else None
    hits = matched.hits if matched else []
    media = next((h.archive_media for h in hits if h.archive_id == archive_id), None)
    data_root: Path = request.app.state.data_root
    path = (data_root / media).resolve() if media else None
    if path is None or not path.is_relative_to(data_root.resolve()) or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no archive media for this match")
    return FileResponse(path)


@desk.post("/translate")
def translate_rationale(request: Request, body: TranslateRequest) -> TranslateResponse:
    """Checkers write the rationale in English; the public also reads it in Nepali."""
    translator: tuple[Reasoner, str] | None = request.app.state.translator
    if translator is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "translation needs a model")
    try:
        nepali, issue = translate(body.english, translator, request.app.state.nepali_checker)
    except (ReasonerUnavailable, StructuredOutputError, httpx.HTTPError) as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "translation failed; write the Nepali by hand"
        ) from error
    return TranslateResponse(nepali=nepali, issue=issue)


@desk.post("/cases/{case_id}/decision")
def decide(
    session: DbSession,
    case_id: str,
    body: DecisionRequest,
    who: Annotated[str | None, Depends(require_checker)],
) -> DeskCase:
    # A checker's own code names them; only the operator token may name someone.
    checker = who or (body.checker or "").strip()
    if not checker:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "say who decided")
    case = get_case(session, case_id)
    draft = _draft(case) or {}
    try:
        if body.action is Action.PUBLISH:
            label = body.label or (VerdictLabel(draft["label"]) if "label" in draft else None)
            rationale_en = body.rationale_en or draft.get("rationale_en")
            rationale_ne = body.rationale_ne or draft.get("rationale_ne")
            if label is None or not rationale_en or not rationale_ne:
                raise DecisionError("no draft to publish: give label and both rationales")
            original = str(body.original_url) if body.original_url else None
            publish(session, case, checker, label, rationale_en, rationale_ne, body.note, original)
        elif body.action is Action.REJECT:
            reject(session, case, checker, body.note or "rejected")
        else:
            reopen(session, case, checker, body.note or "reopened")
    except DecisionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    session.flush()
    return detail(case)


def create_app(
    db: Database,
    media_root: Path,
    desk_token: SecretStr | None,
    origin: str,
    data_root: Path = REPO_ROOT / "data",
    translator: tuple[Reasoner, str] | None = None,
    nepali_checker: tuple[Reasoner, str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Hamsa", version="0.1.0")
    app.state.db, app.state.media_root, app.state.desk_token = db, media_root, desk_token
    app.state.data_root = data_root
    app.state.translator, app.state.nepali_checker = translator, nepali_checker
    app.state.limiter = RateLimiter(SUBMISSIONS_PER_MINUTE)
    app.state.failed_sign_ins = RateLimiter(FAILED_SIGN_INS_PER_MINUTE)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(public)
    app.include_router(desk)
    return app


async def save_uploads(
    request: Request, case_id: str, uploads: list[UploadFile]
) -> list[StoredMedia]:
    media_root: Path = request.app.state.media_root
    stored: list[StoredMedia] = []
    for upload in uploads:
        data = await upload.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file over 100 MB")
        suffix = sniff_suffix(data)
        if suffix is None:
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "only jpeg, png, webp, mp4, webm"
            )
        stored.append(save_media(media_root, case_id, data, suffix))
    return stored


def _draft(case: Case) -> dict[str, Any] | None:
    outputs: dict[str, Any] = case.outputs or {}
    return outputs.get("verdict")


def needs_media(case: Case) -> bool:
    """The worker tried the pasted link and got nothing, so the submitter is asked for the file."""
    tried = case.status not in (CaseStatus.RECEIVED, CaseStatus.PROCESSING)
    return tried and bool(case.source_url) and not case.media


def public_view(session: Session, case: Case) -> PublicCase:
    # A repeat merged into a decided report shows that verdict on its own page; the files
    # belong to the earlier report, which the page links to.
    answer = answered_by(session, case)
    verdict = published_verdict(answer) if answer.status is CaseStatus.PUBLISHED else None
    if verdict and answer is not case:
        verdict = verdict.model_copy(update={"media": []})
    return PublicCase(
        id=case.id,
        status=case.status,
        created_at=case.created_at,
        text=case.text,
        source_url=case.source_url,
        media_count=len(case.media),
        timeline=[PublicStep(at=e.at, status=e.to_status) for e in case.events],
        merged_into=case.merged_into,
        verdict=verdict,
        needs_media=needs_media(case),
    )


def published_verdict(case: Case) -> PublishedVerdict | None:
    if case.final_label is None or not case.final_rationale_en or not case.final_rationale_ne:
        return None
    sources: list[Source] = []
    claim: PublicClaim | None = None
    footage: dict[str, EarlierFootage] = {}  # one entry per archive item, not per frame
    if case.outputs:
        outputs = outputs_from_json(case.outputs)
        if outputs.verdict and outputs.evidence:
            for citation in outputs.verdict.citations:
                passage = outputs.evidence.by_id(citation.passage_id)
                if passage and all(source.url != passage.url for source in sources):
                    sources.append(
                        Source(name=passage.source, url=passage.url, stance=citation.stance)
                    )
        if outputs.claim:
            claim = PublicClaim.model_validate(outputs.claim, from_attributes=True)
        for hit in outputs.media_match.hits if outputs.media_match else []:
            footage.setdefault(
                hit.archive_id, EarlierFootage.model_validate(hit, from_attributes=True)
            )
    return PublishedVerdict(
        label=VerdictLabel(case.final_label),
        rationale_en=case.final_rationale_en,
        rationale_ne=case.final_rationale_ne,
        sources=sources,
        published_at=case.updated_at,
        claim=claim,
        earlier_footage=list(footage.values()),
        media=[m.filename for m in case.media],
    )


def summary(case: Case) -> DeskSummary:
    decision: dict[str, Any] = case.decision or {}
    outputs: dict[str, Any] = case.outputs or {}
    claim: dict[str, Any] = outputs.get("claim") or {}
    draft = _draft(case)
    return DeskSummary(
        id=case.id,
        created_at=case.created_at,
        route=Route(case.route) if case.route else None,
        reasons=decision.get("reasons", []),
        proposed_label=VerdictLabel(draft["label"]) if draft else None,
        claim_en=claim.get("claim_en"),
        text=case.text,
        media_count=len(case.media),
    )


def detail(case: Case) -> DeskCase:
    events: list[CaseEvent] = case.events
    return DeskCase(
        **summary(case).model_dump(),
        status=case.status,
        source_url=case.source_url,
        media=[m.filename for m in case.media],
        outputs=case.outputs,
        decision=case.decision,
        seconds=case.seconds,
        final_label=VerdictLabel(case.final_label) if case.final_label else None,
        events=[
            DeskEvent(
                at=e.at,
                actor=e.actor,
                from_status=e.from_status,
                to_status=e.to_status,
                note=e.note,
            )
            for e in events
        ],
    )


def default_app() -> FastAPI:
    settings = get_settings()
    db = Database(settings.database_url)
    db.create_all()
    # Without a Groq key the desk still drafts the Nepali on the local model (ADR 0001), but
    # unchecked: it garbled disaster words in 5 of 5 sentences and its own check passed all 5
    # (2026-10-23), so every local translation comes with "read every word".
    translator: tuple[Reasoner, str] = (
        OllamaClient(str(settings.ollama_host)),
        settings.vision_model,
    )
    checker: tuple[Reasoner, str] | None = None
    if settings.groq_api_key is not None:
        key = settings.groq_api_key.get_secret_value()
        translator = (GroqClient(key), settings.reasoning_model)
        checker = (GroqClient(key, reasoning_effort="low"), settings.checking_model)
    return create_app(
        db,
        settings.media_root,
        settings.desk_token,
        settings.frontend_origin,
        translator=translator,
        nepali_checker=checker,
    )
