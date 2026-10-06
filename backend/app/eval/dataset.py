"""Ground-truth eval set: hand-labelled posts from the August 2026 Nepal floods.

Labels describe what is true about a post, not what the pipeline outputs, so this
schema stays fixed while pipeline internals change. A scorer maps pipeline output
onto these labels.
"""

import csv
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl, model_validator

LIST_SEPARATOR = "|"


class Platform(StrEnum):
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    X = "x"
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    NEWS_SITE = "news_site"
    OTHER = "other"


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    TEXT = "text"


class Language(StrEnum):
    NEPALI = "ne"
    ENGLISH = "en"
    MIXED = "mixed"
    OTHER = "other"


class Verdict(StrEnum):
    FALSE = "false"
    MISLEADING = "misleading"
    TRUE = "true"
    UNVERIFIABLE = "unverifiable"


class Tactic(StrEnum):
    """How the post misleads. `none` is only valid for true posts."""

    RECYCLED = "recycled"  # real media from another event, place, or time
    MISCAPTIONED = "miscaptioned"  # real media from this event, false claim attached
    EDITED = "edited"  # cropped, spliced, or doctored
    SYNTHETIC = "synthetic"  # ai-generated or cgi
    FABRICATED_TEXT = "fabricated_text"  # invented numbers, quotes, notices
    NONE = "none"


def _blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


def _split_list(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(LIST_SEPARATOR) if part.strip()]
    return value


BlankIsNone = BeforeValidator(_blank_to_none)
PipeList = BeforeValidator(_split_list)


class EvalItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: Annotated[str, Field(pattern=r"^h\d{3}$")]
    kind: MediaKind
    platform: Platform
    language: Language
    claim_text: Annotated[str, Field(min_length=1)]
    claim_text_en: Annotated[str | None, BlankIsNone] = None
    post_url: Annotated[HttpUrl | None, BlankIsNone] = None
    post_archive_url: Annotated[HttpUrl | None, BlankIsNone] = None
    posted_on: Annotated[date | None, BlankIsNone] = None
    media_file: Annotated[str | None, BlankIsNone] = None

    verdict: Verdict
    tactic: Tactic
    original_source_url: Annotated[HttpUrl | None, BlankIsNone] = None
    original_context: Annotated[str | None, BlankIsNone] = None
    original_media_file: Annotated[str | None, BlankIsNone] = None
    fact_check_url: Annotated[HttpUrl | None, BlankIsNone] = None
    evidence_urls: Annotated[list[HttpUrl], PipeList] = []

    notes: Annotated[str | None, BlankIsNone] = None

    @model_validator(mode="after")
    def _labels_are_consistent(self) -> Self:
        if self.verdict is Verdict.TRUE and self.tactic is not Tactic.NONE:
            raise ValueError("a true post cannot have a misleading tactic; use tactic=none")
        if self.verdict in (Verdict.FALSE, Verdict.MISLEADING) and self.tactic is Tactic.NONE:
            raise ValueError(f"a {self.verdict} post needs a tactic other than none")
        if self.verdict is not Verdict.UNVERIFIABLE and not (
            self.fact_check_url or self.evidence_urls
        ):
            raise ValueError("cite a fact_check_url or at least one evidence_url")
        if self.tactic is Tactic.RECYCLED and not (
            self.original_source_url and self.original_context
        ):
            raise ValueError("recycled media needs original_source_url and original_context")
        if self.kind is not MediaKind.TEXT and not self.media_file:
            raise ValueError(f"a {self.kind} post needs media_file")
        if not (self.post_url or self.post_archive_url or self.media_file):
            raise ValueError("keep at least one of post_url, post_archive_url, media_file")
        return self


class DatasetError(Exception):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def load_items(csv_path: Path, media_dir: Path | None = None) -> list[EvalItem]:
    """Parse and validate every row, collecting all problems before failing.

    If `media_dir` is given, referenced media files must exist in it.
    """
    items: list[EvalItem] = []
    problems: list[str] = []
    seen: set[str] = set()

    with csv_path.open(newline="", encoding="utf-8") as handle:
        # Row 1 is the header, so data rows start at line 2 in a spreadsheet.
        for line, row in enumerate(csv.DictReader(handle), start=2):
            label = f"line {line} ({row.get('id') or 'no id'})"
            try:
                item = EvalItem.model_validate(row)
            except ValueError as error:
                problems.append(f"{label}: {error}")
                continue
            if item.id in seen:
                problems.append(f"{label}: duplicate id")
            seen.add(item.id)
            if media_dir is not None:
                for name in (item.media_file, item.original_media_file):
                    if name and not (media_dir / name).is_file():
                        problems.append(f"{label}: missing media file {name}")
            items.append(item)

    if problems:
        raise DatasetError(problems)
    return items
