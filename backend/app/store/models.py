"""SQLite schema: cases, their media, jobs, and the audit trail (ADR 0005)."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Dialect,
    Enum,
    ForeignKey,
    Index,
    String,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class CaseStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    ROUTED = "routed"
    MERGED = "merged"
    PUBLISHED = "published"
    REJECTED = "rejected"


class Channel(StrEnum):
    WEB = "web"
    TELEGRAM = "telegram"
    MESSENGER = "messenger"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


class UTCDateTime(TypeDecorator[datetime]):
    """Stores naive UTC (SQLite has no time zones) and always loads aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: pass an aware UTC datetime")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


def enum_column[E: StrEnum](enum: type[E]) -> Enum:
    """Stores the lowercase value ("routed"), not the member name, and loads the enum."""
    return Enum(enum, native_enum=False, length=16, values_callable=_values)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        dict[str, Any]: JSON,
        datetime: UTCDateTime,
        CaseStatus: enum_column(CaseStatus),
        Channel: enum_column(Channel),
        JobState: enum_column(JobState),
    }


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    channel: Mapped[Channel]
    text: Mapped[str | None]
    source_url: Mapped[str | None]
    status: Mapped[CaseStatus] = mapped_column(default=CaseStatus.RECEIVED, index=True)

    # Set by the worker: the serialised StageOutputs, RouteDecision, and stage timings.
    outputs: Mapped[dict[str, Any] | None]
    decision: Mapped[dict[str, Any] | None]
    seconds: Mapped[dict[str, Any] | None]
    route: Mapped[str | None] = mapped_column(String(16), index=True)
    merged_into: Mapped[str | None] = mapped_column(ForeignKey("cases.id"))

    # Set by the checker: what was published, which may differ from the model's draft.
    final_label: Mapped[str | None] = mapped_column(String(16))
    final_rationale_en: Mapped[str | None]
    final_rationale_ne: Mapped[str | None]

    media: Mapped[list["Media"]] = relationship(back_populates="case", order_by="Media.id")
    events: Mapped[list["CaseEvent"]] = relationship(order_by="CaseEvent.id")


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    filename: Mapped[str]  # stored name inside the case's media directory
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int]

    case: Mapped[Case] = relationship(back_populates="media")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "state", "not_before"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    state: Mapped[JobState] = mapped_column(default=JobState.QUEUED)
    attempts: Mapped[int] = mapped_column(default=0)
    not_before: Mapped[datetime] = mapped_column(default=utcnow)  # retry backoff
    lease_until: Mapped[datetime | None]  # a running job past this is presumed dead
    last_error: Mapped[str | None]


class Checker(Base):
    """A fact-checker with their own access code. Only the code's hash is kept."""

    __tablename__ = "checkers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    code_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    active: Mapped[bool] = mapped_column(default=True)


class TelegramReport(Base):
    """The chat a submission came from, so the bot can send the verdict back. Messenger
    chats live here too (chat_id is the page-scoped user id); the case's channel says
    which platform. shortcut: named for Telegram; rename once the schema has migrations."""

    __tablename__ = "telegram_reports"

    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)  # Telegram ids exceed 32 bits
    message_id: Mapped[int]
    # The last case event the submitter heard about; event ids only grow, so a
    # verdict corrected after a reopen is a newer event and is sent again.
    told_event: Mapped[int] = mapped_column(default=0)
    asked_for_media: Mapped[bool] = mapped_column(default=False)


class PostId(Base):
    """The platform's own id for a linked post, from yt-dlp: it survives share links,
    redirects and tracking parameters, so a forwarded post is known as a repeat."""

    __tablename__ = "post_ids"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), unique=True)
    post_id: Mapped[str] = mapped_column(index=True)


class Lesson(Base):
    """A published case the archive has still to learn from (worker, ADR 0011)."""

    __tablename__ = "lessons"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    # Where the checker found the original footage, for a refuted case.
    original_url: Mapped[str | None]
    done_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    error: Mapped[str | None]


class CaseEvent(Base):
    """Every status change, who made it, and why: the audit trail behind a verdict."""

    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    at: Mapped[datetime] = mapped_column(default=utcnow)
    actor: Mapped[str]  # "system" or a checker's name
    from_status: Mapped[str | None] = mapped_column(String(16))
    to_status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str | None]
