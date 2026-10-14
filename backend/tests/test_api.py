import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import SecretStr

from app.api.main import RateLimiter, create_app, sniff_suffix
from app.store.cases import Database
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
    assert client.get(f"/cases/{case_id}").json() == {
        "id": case_id,
        "status": "received",
        "verdict": None,
        "needs_media": False,
    }


@pytest.mark.parametrize(
    ("data", "files", "code"),
    [
        ({}, None, 422),
        ({"text": "   "}, None, 422),
        ({"text": "x", "url": "not a url"}, None, 422),
        ({}, [("files", ("x.jpg", b"<script>", "image/jpeg"))], 415),
    ],
    ids=["empty", "blank-text", "bad-url", "fake-image"],
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
    assert body == {"id": "c1", "status": "routed", "verdict": None, "needs_media": False}


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
        json={"action": "publish", "checker": "sita", "label": "misleading"},
    )
    assert client.get("/cases/c1").json()["verdict"]["label"] == "misleading"


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
