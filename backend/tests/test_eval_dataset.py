import csv
from pathlib import Path

import pytest

from app.eval.dataset import DatasetError, EvalItem, Tactic, Verdict, load_items

RECYCLED_VIDEO = {
    "id": "h001",
    "kind": "video",
    "platform": "tiktok",
    "language": "ne",
    "claim_text": "मेलम्ची बजार बगायो",
    "post_url": "https://www.tiktok.com/@someone/video/1",
    "media_file": "h001.mp4",
    "verdict": "false",
    "tactic": "recycled",
    "original_source_url": "https://www.youtube.com/watch?v=abc",
    "original_context": "2023 Himachal Pradesh floods, Kullu",
    "fact_check_url": "https://nepalfactcheck.org/2026/08/example",
}

TRUE_IMAGE = {
    "id": "h002",
    "kind": "image",
    "platform": "facebook",
    "language": "en",
    "claim_text": "Bridge at Sindhupalchok washed away",
    "media_file": "h002.jpg",
    "verdict": "true",
    "tactic": "none",
    "evidence_urls": "https://kathmandupost.com/a | https://onlinekhabar.com/b",
}


def write_csv(path: Path, rows: list[dict[str, str]]) -> Path:
    fields = list(EvalItem.model_fields)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
    return path


def test_loads_valid_rows_from_spreadsheet_csv(tmp_path: Path) -> None:
    items = load_items(write_csv(tmp_path / "items.csv", [RECYCLED_VIDEO, TRUE_IMAGE]))

    recycled, genuine = items
    assert recycled.tactic is Tactic.RECYCLED
    assert recycled.claim_text_en is None  # blank cell, not empty string
    assert genuine.verdict is Verdict.TRUE
    assert [str(url) for url in genuine.evidence_urls] == [
        "https://kathmandupost.com/a",
        "https://onlinekhabar.com/b",
    ]


def test_template_header_matches_schema() -> None:
    template = Path(__file__).resolve().parents[2] / "data" / "eval" / "items.csv"
    with template.open(encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header == list(EvalItem.model_fields)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"tactic": "none"}, "needs a tactic"),
        ({"verdict": "true"}, "cannot have a misleading tactic"),
        ({"fact_check_url": ""}, "cite a fact_check_url"),
        ({"original_context": ""}, "original_source_url and original_context"),
        ({"media_file": ""}, "needs media_file"),
        ({"id": "1"}, "should match pattern"),
        ({"verdict": "fake"}, "Input should be"),
    ],
)
def test_rejects_inconsistent_labels(overrides: dict[str, str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        EvalItem.model_validate(RECYCLED_VIDEO | overrides)


def test_text_only_unverifiable_claim_needs_no_citation() -> None:
    item = EvalItem.model_validate(
        {
            "id": "h003",
            "kind": "text",
            "platform": "whatsapp",
            "language": "ne",
            "claim_text": "बाँध फुट्दैछ, तुरुन्त भाग्नुहोस्",
            "post_archive_url": "https://archive.ph/xyz",
            "verdict": "unverifiable",
            "tactic": "fabricated_text",
        }
    )
    assert item.media_file is None


def test_reports_every_problem_with_spreadsheet_line_numbers(tmp_path: Path) -> None:
    bad = RECYCLED_VIDEO | {"id": "h004", "tactic": "none"}
    duplicate = TRUE_IMAGE | {"id": "h001"}
    path = write_csv(tmp_path / "items.csv", [RECYCLED_VIDEO, bad, duplicate])

    with pytest.raises(DatasetError) as caught:
        load_items(path)

    problems = caught.value.problems
    assert len(problems) == 2
    assert problems[0].startswith("line 3 (h004)")
    assert problems[1] == "line 4 (h001): duplicate id"


def test_checks_media_files_exist(tmp_path: Path) -> None:
    media = tmp_path / "media"
    media.mkdir()
    (media / "h002.jpg").write_bytes(b"")
    path = write_csv(tmp_path / "items.csv", [RECYCLED_VIDEO, TRUE_IMAGE])

    with pytest.raises(DatasetError) as caught:
        load_items(path, media_dir=media)

    assert caught.value.problems == ["line 2 (h001): missing media file h001.mp4"]
