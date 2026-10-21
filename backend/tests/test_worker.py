import subprocess
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from app.ingest.download import Downloaded
from app.pipeline.contracts import Route, Stage, StageFailure, VerdictLabel
from app.pipeline.run import Result
from app.router.route import StageOutputs
from app.store.cases import Database, StoredMedia, create_case, open_claims
from app.store.models import Case, CaseStatus, Channel, Job, JobState
from app.worker import MAX_ATTEMPTS, process_next
from tests.factories import claim, outputs
from tests.stored import add_case, add_routed_case, database, routed_result


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return database(tmp_path)


def transient_failure(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
    failure = StageFailure(stage=Stage.EXTRACT, error="ConnectError: ollama down", transient=True)
    return routed_result(StageOutputs(failures=(failure,)))


def force_due(db: Database) -> None:
    with db.session.begin() as session:
        job = session.get_one(Job, 1)
        job.not_before = job.not_before.replace(year=2000)


def test_nothing_to_do(db: Database, tmp_path: Path) -> None:
    assert process_next(db, lambda t, m, p: routed_result(), tmp_path) is None


def test_runs_the_pipeline_with_the_case_text_and_media_paths(db: Database, tmp_path: Path) -> None:
    add_case(db, "c1", text="बाढी आयो")
    seen: list[tuple[str | None, list[Path]]] = []

    def runner(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        seen.append((text, list(media)))
        return routed_result()

    assert process_next(db, runner, tmp_path) == "c1"
    assert seen == [("बाढी आयो", [])]
    with db.session() as session:
        assert session.get_one(Case, "c1").status is CaseStatus.ROUTED


def test_transient_failure_is_retried_then_sent_to_a_human(db: Database, tmp_path: Path) -> None:
    add_case(db, "c1")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        force_due(db)
        process_next(db, transient_failure, tmp_path)
        with db.session() as session:
            job = session.get_one(Job, 1)
            case = session.get_one(Case, "c1")
            if attempt < MAX_ATTEMPTS:
                assert job.state is JobState.QUEUED
                assert job.last_error == "ConnectError: ollama down"
            else:
                assert job.state is JobState.DONE
                assert case.route == Route.HUMAN_REVIEW.value


def test_pipeline_bug_routes_to_a_human_instead_of_looping(db: Database, tmp_path: Path) -> None:
    add_case(db, "c1")

    def broken(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        raise ValueError("router bug")

    process_next(db, broken, tmp_path)
    with db.session() as session:
        case = session.get_one(Case, "c1")
        assert case.route == Route.HUMAN_REVIEW.value
        assert case.decision is not None
        assert case.decision["reasons"] == ["pipeline error: ValueError"]


def add_with_file(db: Database, case_id: str, sha256: str) -> None:
    with db.session.begin() as session:
        create_case(session, case_id, Channel.WEB, None, None, [StoredMedia("a.mp4", sha256, 10)])


def test_identical_file_is_merged_without_running_the_pipeline(
    db: Database, tmp_path: Path
) -> None:
    add_with_file(db, "c1", "f" * 64)
    add_with_file(db, "c2", "f" * 64)
    runs: list[str | None] = []

    def runner(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        runs.append(text)
        return routed_result()

    assert process_next(db, runner, tmp_path) == "c1"
    assert process_next(db, runner, tmp_path) == "c2"
    assert len(runs) == 1
    with db.session() as session:
        merged = session.get_one(Case, "c2")
        assert merged.status is CaseStatus.MERGED
        assert merged.merged_into == "c1"


def test_open_claims_are_the_routed_checkable_ones(db: Database) -> None:
    add_routed_case(db, "c1", routed_result(outputs(claim=claim(places=["Melamchi"]))))
    add_routed_case(db, "c2", routed_result(outputs(claim=claim(checkable=False))))
    with db.session() as session:
        waiting = open_claims(session)
    assert [(c.case_id, c.places) for c in waiting] == [("c1", ("Melamchi",))]


def add_link_case(db: Database, case_id: str) -> None:
    with db.session.begin() as session:
        create_case(session, case_id, Channel.WEB, None, "https://www.tiktok.com/@x/video/1", [])


def test_a_pasted_link_is_fetched_and_checked_like_an_upload(db: Database, tmp_path: Path) -> None:
    add_link_case(db, "c1")
    mp4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64

    def fetch(url: str, folder: Path) -> Downloaded:
        (folder / "post.mp4").write_bytes(mp4)
        (folder / "post.txt").write_bytes(b"not media")  # dropped: not an upload type
        return Downloaded(sorted(folder.iterdir()), "रसुवामा हिमताल फुट्यो")

    seen: list[tuple[str | None, list[Path]]] = []

    def runner(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        seen.append((text, list(media)))
        return routed_result()

    assert process_next(db, runner, tmp_path, fetch) == "c1"
    [(caption, [path])] = seen
    assert caption == "रसुवामा हिमताल फुट्यो"  # the post's caption is the claim
    assert path.read_bytes() == mp4
    with db.session() as session:
        assert len(session.get_one(Case, "c1").media) == 1


def test_the_posts_caption_and_date_come_with_the_link(db: Database, tmp_path: Path) -> None:
    with db.session.begin() as session:
        create_case(session, "c1", Channel.WEB, "is this real?", "https://x.com/a/status/1", [])

    def fetch(url: str, folder: Path) -> Downloaded:
        return Downloaded([], "बुढीगण्डकीमा बाढी", uploaded=date(2026, 10, 11))

    seen: list[tuple[str | None, date | None]] = []

    def runner(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        seen.append((text, posted))
        return routed_result()

    assert process_next(db, runner, tmp_path, fetch) == "c1"
    # The caption leads; the sender's note follows as context.
    assert seen == [("बुढीगण्डकीमा बाढी\n\nSender's note: is this real?", date(2026, 10, 11))]


def test_a_post_that_could_not_be_opened_goes_to_a_checker_unread(
    db: Database, tmp_path: Path
) -> None:
    add_link_case(db, "c1")

    def fetch(url: str, folder: Path) -> Downloaded:
        raise subprocess.CalledProcessError(1, "yt-dlp", stderr="HTTP Error 404")

    def runner(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        raise AssertionError("no model may be asked about an empty post")

    assert process_next(db, runner, tmp_path, fetch) == "c1"
    with db.session() as session:
        case = session.get_one(Case, "c1")
        assert case.route == Route.HUMAN_REVIEW.value
        assert case.decision is not None
        [reason] = case.decision["reasons"]  # not "pipeline error": the runner never ran
        assert "could not be opened" in reason


def test_a_link_that_cannot_be_fetched_is_checked_on_its_text(db: Database, tmp_path: Path) -> None:
    with db.session.begin() as session:
        create_case(session, "c1", Channel.WEB, "रसुवामा बाढी", "https://x.com/a/status/1", [])

    def fetch(url: str, folder: Path) -> Downloaded:
        raise subprocess.CalledProcessError(1, "yt-dlp", stderr="login required")

    seen: list[list[Path]] = []

    def runner(text: str | None, media: Sequence[Path], posted: date | None) -> Result:
        seen.append(list(media))
        return routed_result()

    assert process_next(db, runner, tmp_path, fetch) == "c1"
    assert seen == [[]]


def test_download_retries_without_the_browser_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ingest import download as module

    commands: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "--cookies-from-browser" in command:
            raise subprocess.CalledProcessError(1, command, stderr="page needs to be reloaded")
        (tmp_path / "post.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.download("https://youtu.be/x", tmp_path, browser="firefox").files == [
        tmp_path / "post.mp4"
    ]
    assert ["--cookies-from-browser" in c for c in commands] == [True, False]


def test_published_cases_are_learned_once_and_failures_recorded(db: Database) -> None:
    from app.learn import Verdicted
    from app.store.cases import publish
    from app.store.models import Lesson
    from app.worker import learn_next

    for case_id in ("c1", "c2"):
        add_routed_case(db, case_id)
        with db.session.begin() as session:
            case = session.get_one(Case, case_id)
            publish(session, case, "sita", VerdictLabel.FALSE, "en", "ne", None, None)
    taught: list[str] = []

    def teach(verdicted: Verdicted) -> list[str]:
        if verdicted.case_id == "c2":
            raise ValueError("dead link")
        taught.append(verdicted.page_url)
        return ["case-c1-0"]

    assert learn_next(db, Path("/media"), "http://site", teach)
    assert learn_next(db, Path("/media"), "http://site", teach)
    assert not learn_next(db, Path("/media"), "http://site", teach)  # nothing left
    assert taught == ["http://site/check/c1"]
    with db.session() as session:
        c1, c2 = session.scalars(select(Lesson).order_by(Lesson.id)).all()
        assert c1.done_at is not None
        assert c2.error == "ValueError: dead link"
