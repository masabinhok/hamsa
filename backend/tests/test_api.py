import io
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from app.api.main import RateLimiter, create_app, sniff_suffix
from app.pipeline.contracts import Duplicate, DuplicateBasis
from app.store.cases import Database, claim_job, complete_job
from app.store.models import Case
from tests.factories import cite, hit, outputs, passage, verdict
from tests.images import photo
from tests.stored import add_routed_case, database, routed_result

TOKEN = "desk-secret"  # noqa: S105 - test-only token
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return database(tmp_path)


@pytest.fixture
def client(db: Database, tmp_path: Path) -> TestClient:
    app = create_app(
        db, tmp_path / "media", SecretStr(TOKEN), "http://localhost:3000", tmp_path / "data"
    )
    return TestClient(app)


def jpeg() -> bytes:
    buffer = io.BytesIO()
    photo(1).save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("head", "suffix"),
    [
        (b"\xff\xd8\xff\xe0", ".jpg"),
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"RIFF\x00\x00\x00\x00WEBP", ".webp"),
        (b"\x00\x00\x00\x18ftypmp42", ".mp4"),
        (b"\x1a\x45\xdf\xa3", ".webm"),
        (b"<html>", None),
    ],
)
def test_media_type_is_sniffed_from_content(head: bytes, suffix: str | None) -> None:
    assert sniff_suffix(head + b"\x00" * 16) == suffix


# public endpoints


def test_submit_text_and_image(client: TestClient, tmp_path: Path) -> None:
    response = client.post(
        "/cases",
        data={"text": "  रसुवामा हिमताल फुट्यो  ", "url": "https://facebook.com/post/1"},
        files=[("files", ("anything.bin", jpeg(), "application/octet-stream"))],
    )
    assert response.status_code == 202
    case_id = response.json()["id"]
    [stored] = (tmp_path / "media" / case_id).iterdir()
    assert stored.suffix == ".jpg"  # from the bytes, not the client's file name
    public = client.get(f"/cases/{case_id}").json()
    assert public["status"] == "received"
    assert public["text"] == "रसुवामा हिमताल फुट्यो"
    assert public["source_url"] == "https://facebook.com/post/1"
    assert public["media_count"] == 1
    assert [step["status"] for step in public["timeline"]] == ["received"]
    assert public["verdict"] is None


@pytest.mark.parametrize(
    ("data", "files", "code"),
    [
        ({}, None, 422),
        ({"text": "   "}, None, 422),
        ({"text": "x", "url": "not a url"}, None, 422),
        ({"url": "https://github.com/a/b"}, None, 422),
        ({"url": "http://127.0.0.1:6333/collections"}, None, 422),
        ({}, [("files", ("x.jpg", b"<script>", "image/jpeg"))], 415),
    ],
    ids=["empty", "blank-text", "bad-url", "other-site", "internal-address", "fake-image"],
)
def test_bad_submissions_are_rejected(
    client: TestClient,
    data: dict[str, str],
    files: list[tuple[str, tuple[str, bytes, str]]] | None,
    code: int,
) -> None:
    assert client.post("/cases", data=data, files=files).status_code == code


def test_too_many_files_are_rejected(client: TestClient) -> None:
    files = [("files", (f"{i}.jpg", jpeg(), "image/jpeg")) for i in range(5)]
    assert client.post("/cases", files=files).status_code == 413


def test_unknown_case_is_404(client: TestClient) -> None:
    assert client.get("/cases/nope").status_code == 404


def test_public_view_never_shows_the_model_draft(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c1")
    body = client.get("/cases/c1").json()
    assert body["status"] == "routed"
    assert body["verdict"] is None
    assert not {"outputs", "decision", "reasons", "proposed_label", "claim_en"} & set(body)


# desk


def test_desk_needs_the_token(client: TestClient) -> None:
    assert client.get("/desk/queue").status_code == 401
    assert client.get("/desk/queue", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/desk/queue", headers=AUTH).status_code == 200


def test_desk_is_disabled_without_a_configured_token(db: Database, tmp_path: Path) -> None:
    app = create_app(db, tmp_path, None, "http://localhost:3000")
    assert TestClient(app).get("/desk/queue", headers=AUTH).status_code == 503


def test_queue_lists_fast_track_first_with_reasons(client: TestClient, db: Database) -> None:
    add_routed_case(db, "review")
    add_routed_case(db, "fast", routed_result(outputs(hits=[hit()], verdict=verdict("false", 0.5))))
    queue = client.get("/desk/queue", headers=AUTH).json()
    assert [(c["id"], c["route"]) for c in queue] == [
        ("fast", "fast_track"),
        ("review", "human_review"),
    ]
    assert queue[0]["reasons"] == ["recycled media: matches 2023 Himachal Pradesh floods, Kullu"]
    assert queue[0]["proposed_label"] == "false"


def test_publish_with_one_click_uses_the_draft_and_cites_sources(
    client: TestClient, db: Database
) -> None:
    same_article = {"source_kind": "fact_check", "url": "https://example.org/debunk"}
    case = outputs(
        passages=[
            passage("p1", "Nepal Factcheck", **same_article),
            passage("p2", "Nepal Factcheck", **same_article),
        ],
        verdict=verdict("false", 0.9, citations=[cite("p1"), cite("p2")]),
    )
    add_routed_case(db, "c1", routed_result(case))

    response = client.post(
        "/desk/cases/c1/decision", headers=AUTH, json={"action": "publish", "checker": "sita"}
    )

    assert response.status_code == 200
    assert response.json()["events"][-1]["actor"] == "sita"
    public = client.get("/cases/c1").json()
    assert public["status"] == "published"
    assert public["verdict"]["label"] == "false"
    assert public["verdict"]["rationale_ne"] == "यो भिडियो पुरानो हो।"
    assert public["verdict"]["sources"] == [
        {"name": "Nepal Factcheck", "url": "https://example.org/debunk", "stance": "refutes"}
    ]
    assert [v["id"] for v in client.get("/verdicts").json()] == ["c1"]


def test_checker_can_override_the_label(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c1")
    client.post(
        "/desk/cases/c1/decision",
        headers=AUTH,
        json={
            "action": "publish",
            "checker": "sita",
            "label": "misleading",
            "rationale_en": "Real footage, wrong year.",
            "rationale_ne": "साँचो भिडियो, फरक वर्ष।",
        },
    )
    assert client.get("/cases/c1").json()["verdict"]["label"] == "misleading"


def test_a_new_label_needs_its_own_reasoning(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c1")  # the draft says false
    body = {"action": "publish", "checker": "sita", "label": "true"}
    response = client.post("/desk/cases/c1/decision", headers=AUTH, json=body)
    assert response.status_code == 422
    assert client.get("/cases/c1").json()["verdict"] is None


def test_deciding_twice_conflicts(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c1")
    body = {"action": "reject", "checker": "sita", "note": "opinion"}
    assert client.post("/desk/cases/c1/decision", headers=AUTH, json=body).status_code == 200
    assert client.post("/desk/cases/c1/decision", headers=AUTH, json=body).status_code == 409


def test_media_is_served_only_by_known_name(client: TestClient) -> None:
    case_id = client.post("/cases", files=[("files", ("a.jpg", jpeg(), "image/jpeg"))]).json()["id"]
    [name] = client.get(f"/desk/cases/{case_id}", headers=AUTH).json()["media"]

    served = client.get(f"/desk/cases/{case_id}/media/{name}", headers=AUTH)
    assert served.status_code == 200
    assert Image.open(io.BytesIO(served.content)).format == "JPEG"
    traversal = client.get(f"/desk/cases/{case_id}/media/..%2F..%2Fhamsa.db", headers=AUTH)
    assert traversal.status_code == 404


def test_rate_limiter_uses_a_sliding_window() -> None:
    limiter = RateLimiter(limit=2, window_s=60)
    assert limiter.allow("1.2.3.4", now=0)
    assert limiter.allow("1.2.3.4", now=10)
    assert not limiter.allow("1.2.3.4", now=20)
    assert limiter.allow("5.6.7.8", now=20)  # other clients are unaffected
    assert limiter.allow("1.2.3.4", now=61)  # the first hit left the window


def test_submissions_are_rate_limited_per_client(client: TestClient) -> None:
    codes = [client.post("/cases", data={"text": f"claim {i}"}).status_code for i in range(11)]
    assert codes == [202] * 10 + [429]


def test_archive_original_is_served_only_for_a_match_inside_data(
    client: TestClient, db: Database, tmp_path: Path
) -> None:
    clip = tmp_path / "data" / "archive" / "media" / "kullu.mp4"
    clip.parent.mkdir(parents=True)
    clip.write_bytes(b"video")
    (tmp_path / "secret.txt").write_text("not for checkers")
    hits = [
        hit(archive_id="kullu", archive_media="archive/media/kullu.mp4", archive_seconds=4.0),
        hit(archive_id="escape", archive_media="../secret.txt"),
    ]
    add_routed_case(db, "c1", routed_result(outputs(hits=hits)))

    served = client.get("/desk/cases/c1/archive/kullu", headers=AUTH)
    assert served.status_code == 200
    assert served.content == b"video"
    assert client.get("/desk/cases/c1/archive/escape", headers=AUTH).status_code == 404
    assert client.get("/desk/cases/c1/archive/unknown", headers=AUTH).status_code == 404
    assert client.get("/desk/cases/c1/archive/kullu").status_code == 401


def test_public_case_asks_for_the_file_when_the_link_failed(
    client: TestClient, db: Database
) -> None:
    case_id = client.post("/cases", data={"url": "https://www.facebook.com/reel/1"}).json()["id"]
    assert client.get(f"/cases/{case_id}").json()["needs_media"] is False  # not tried yet
    add_routed_case(db, "c9")
    with db.session.begin() as session:
        session.get_one(Case, "c9").source_url = "https://www.facebook.com/reel/1"
    assert client.get("/cases/c9").json()["needs_media"] is True


def test_the_sender_adds_the_file_to_the_same_report(
    client: TestClient, db: Database, tmp_path: Path
) -> None:
    add_routed_case(db, "c9")
    with db.session.begin() as session:
        session.get_one(Case, "c9").source_url = "https://www.facebook.com/reel/1"
    sent = client.post("/cases/c9/media", files=[("files", ("a.jpg", jpeg(), "image/jpeg"))])
    assert sent.status_code == 200
    report = sent.json()
    assert (report["status"], report["media_count"], report["needs_media"]) == (
        "received",
        1,
        False,
    )
    assert len(list((tmp_path / "media" / "c9").iterdir())) == 1
    with db.session.begin() as session:
        assert claim_job(session) is not None  # queued again, on the same case
    # Once it has its file it is no longer waiting for one; nor is a report without a link.
    again = client.post("/cases/c9/media", files=[("files", ("a.jpg", jpeg(), "image/jpeg"))])
    assert again.status_code == 409
    add_routed_case(db, "c10")
    assert client.post("/cases/c10/media", files=[("files", ("a.jpg", jpeg()))]).status_code == 409


def test_only_photos_and_videos_are_added(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c9")
    with db.session.begin() as session:
        session.get_one(Case, "c9").source_url = "https://www.facebook.com/reel/1"
    bad = client.post("/cases/c9/media", files=[("files", ("a.jpg", b"%PDF-1.7", "image/jpeg"))])
    assert bad.status_code == 415
    assert client.get("/cases/c9").json()["needs_media"] is True


def test_publishing_records_the_original_for_the_archive(client: TestClient, db: Database) -> None:
    from sqlalchemy import select

    from app.store.models import Lesson

    add_routed_case(db, "c1")
    body = {
        "action": "publish",
        "checker": "sita",
        "label": "false",
        "rationale_en": "It is from Alaska.",
        "rationale_ne": "यो अलास्काको हो।",
        "original_url": "https://www.instagram.com/reel/abc/",
    }
    assert client.post("/desk/cases/c1/decision", headers=AUTH, json=body).status_code == 200
    with db.session() as session:
        [lesson] = session.scalars(select(Lesson)).all()
        assert lesson.original_url == "https://www.instagram.com/reel/abc/"


def test_a_checker_signs_in_with_their_own_code_and_is_named_by_it(
    client: TestClient, db: Database
) -> None:
    from app.checkers import add

    with db.session.begin() as session:
        code = add(session, "Sita Sharma")
    mine = {"Authorization": f"Bearer {code}"}
    assert client.get("/desk/me", headers=mine).json() == {"name": "Sita Sharma"}
    assert client.get("/desk/me", headers=AUTH).json() == {"name": None}

    add_routed_case(db, "c1")
    # The body cannot put someone else's name on the decision.
    body = {"action": "reject", "checker": "someone else", "note": "an opinion"}
    assert client.post("/desk/cases/c1/decision", headers=mine, json=body).status_code == 200
    events = client.get("/desk/cases/c1", headers=mine).json()["events"]
    assert events[-1]["actor"] == "Sita Sharma"


def test_a_removed_checker_cannot_sign_in(client: TestClient, db: Database) -> None:
    from app.checkers import add
    from app.store.models import Checker

    with db.session.begin() as session:
        code = add(session, "Ram")
    with db.session.begin() as session:
        session.scalars(select(Checker)).one().active = False
    assert client.get("/desk/me", headers={"Authorization": f"Bearer {code}"}).status_code == 401


def test_the_operator_token_must_say_who_decided(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c1")
    response = client.post("/desk/cases/c1/decision", headers=AUTH, json={"action": "reject"})
    assert response.status_code == 422


def test_desk_works_with_checker_accounts_alone(db: Database, tmp_path: Path) -> None:
    from app.checkers import add

    app = create_app(db, tmp_path / "media", None, "http://localhost:3000", tmp_path / "data")
    assert TestClient(app).get("/desk/queue").status_code == 503  # nobody can sign in yet
    with db.session.begin() as session:
        code = add(session, "Sita")
    response = TestClient(app).get("/desk/queue", headers={"Authorization": f"Bearer {code}"})
    assert response.status_code == 200


def test_uploads_and_readings_are_public_only_once_published(
    client: TestClient, db: Database
) -> None:
    case_id = client.post("/cases", files=[("files", ("a.jpg", jpeg(), "image/jpeg"))]).json()["id"]
    [name] = client.get(f"/desk/cases/{case_id}", headers=AUTH).json()["media"]
    assert client.get(f"/cases/{case_id}/media/{name}").status_code == 404  # not reviewed yet

    result = routed_result(outputs(hits=[hit(), hit(frame_index=3)]))
    with db.session.begin() as session:
        claimed = claim_job(session)
        assert claimed is not None
        case = session.get_one(Case, case_id)
        complete_job(session, claimed[0], case, result.outputs, result.decision, result.seconds)
    assert client.get(f"/cases/{case_id}").json()["verdict"] is None
    publish = {"action": "publish", "checker": "sita"}
    client.post(f"/desk/cases/{case_id}/decision", headers=AUTH, json=publish)

    public = client.get(f"/cases/{case_id}").json()
    assert public["verdict"]["claim"]["claim_en"] == "Melamchi bazaar was swept away"
    assert [f["original_context"] for f in public["verdict"]["earlier_footage"]] == [
        "2023 Himachal Pradesh floods, Kullu"  # two frames of one archive item, shown once
    ]
    assert public["verdict"]["media"] == [name]
    assert [step["status"] for step in public["timeline"]] == [
        "received",
        "processing",
        "routed",
        "published",
    ]
    assert "sita" not in str(public)  # checker names stay on the desk
    assert client.get(f"/cases/{case_id}/media/{name}").status_code == 200
    assert client.get(f"/cases/{case_id}/media/..%2F..%2Fhamsa.db").status_code == 404


def test_a_merged_report_points_to_the_report_it_joined_only_once_decided(
    client: TestClient, db: Database
) -> None:
    add_routed_case(db, "c1")
    add_routed_case(db, "c2")
    with db.session.begin() as session:
        session.get_one(Case, "c2").merged_into = "c1"
    assert client.get("/cases/c2").json()["merged_into"] is None  # c1 is someone else's, open
    client.post(
        "/desk/cases/c1/decision", headers=AUTH, json={"action": "publish", "checker": "sita"}
    )
    assert client.get("/cases/c2").json()["merged_into"] == "c1"


def test_a_published_photo_is_served_without_its_location(client: TestClient, db: Database) -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 degrees to display
    exif[0x8825] = {2: (27.0, 42.0, 0.0), 4: (85.0, 19.0, 0.0)}  # GPS latitude, longitude
    buffer = io.BytesIO()
    photo(1).resize((120, 80)).save(buffer, "JPEG", exif=exif)
    files = [("files", ("a.jpg", buffer.getvalue(), "image/jpeg"))]
    case_id = client.post("/cases", files=files).json()["id"]
    [name] = client.get(f"/desk/cases/{case_id}", headers=AUTH).json()["media"]
    result = routed_result()
    with db.session.begin() as session:
        claimed = claim_job(session)
        assert claimed is not None
        case = session.get_one(Case, case_id)
        complete_job(session, claimed[0], case, result.outputs, result.decision, result.seconds)
    client.post(
        f"/desk/cases/{case_id}/decision",
        headers=AUTH,
        json={"action": "publish", "checker": "sita"},
    )

    public = Image.open(io.BytesIO(client.get(f"/cases/{case_id}/media/{name}").content))
    assert len(public.getexif()) == 0
    assert "xmp" not in public.info
    assert public.size == (80, 120)  # turned upright before the metadata went
    desk = client.get(f"/desk/cases/{case_id}/media/{name}", headers=AUTH)
    assert Image.open(io.BytesIO(desk.content)).getexif().get_ifd(0x8825)  # checkers keep it


def test_wrong_codes_are_throttled_per_client(db: Database, tmp_path: Path) -> None:
    app = create_app(db, tmp_path, SecretStr(TOKEN), "http://localhost:3000")
    guesser = TestClient(app, client=("1.2.3.4", 1))
    wrong = {"Authorization": "Bearer guess"}
    codes = [guesser.get("/desk/me", headers=wrong).status_code for _ in range(11)]
    assert codes == [401] * 10 + [429]
    assert guesser.get("/desk/me", headers=AUTH).status_code == 429  # even the right code
    assert TestClient(app, client=("5.6.7.8", 1)).get("/desk/me", headers=AUTH).status_code == 200


# translation


def translating_client(
    db: Database, tmp_path: Path, *outcomes: dict[str, Any] | Exception
) -> TestClient:
    from tests.test_verdict import FakeReasoner

    translator = FakeReasoner(*outcomes)
    checker = FakeReasoner({"faithful": True, "problem": ""})
    app = create_app(
        db,
        tmp_path / "media",
        SecretStr(TOKEN),
        "http://localhost:3000",
        tmp_path / "data",
        translator=(translator, "translate-model"),
        nepali_checker=(checker, "check-model"),
    )
    return TestClient(app)


def test_a_checkers_english_is_translated_and_checked(db: Database, tmp_path: Path) -> None:
    client = translating_client(db, tmp_path, {"nepali": "भिडियो अलास्काको हो।"})
    response = client.post(
        "/desk/translate", json={"english": "The video is from Alaska."}, headers=AUTH
    )
    assert response.status_code == 200
    assert response.json() == {"nepali": "भिडियो अलास्काको हो।", "issue": None}


@pytest.mark.parametrize("failure", ["groq", "local"])
def test_a_failed_translation_asks_for_the_nepali_by_hand(
    db: Database, tmp_path: Path, failure: str
) -> None:
    import httpx

    from app.llm.groq import ReasonerUnavailable

    down = ReasonerUnavailable("groq down") if failure == "groq" else httpx.ConnectError("down")
    client = translating_client(db, tmp_path, down)
    response = client.post("/desk/translate", json={"english": "The video is old."}, headers=AUTH)
    assert response.status_code == 503
    assert "by hand" in response.json()["detail"]


def test_translation_needs_a_model_and_a_checker(client: TestClient) -> None:
    unconfigured = client.post("/desk/translate", json={"english": "x"}, headers=AUTH)
    assert unconfigured.status_code == 503
    assert client.post("/desk/translate", json={"english": "x"}).status_code == 401


def test_a_repeat_shows_the_verdict_it_was_merged_into(client: TestClient, db: Database) -> None:
    add_routed_case(db, "c1")
    assert client.post(
        "/desk/cases/c1/decision", json={"action": "publish", "checker": "Asha"}, headers=AUTH
    ).is_success
    add_routed_case(
        db,
        "c2",
        routed_result(outputs(duplicate=Duplicate(case_id="c1", basis=DuplicateBasis.LINK))),
    )
    repeat = client.get("/cases/c2").json()
    assert repeat["merged_into"] == "c1"
    assert repeat["verdict"]["label"] == client.get("/cases/c1").json()["verdict"]["label"]
    assert repeat["verdict"]["media"] == []  # served under c1, which the page links to
