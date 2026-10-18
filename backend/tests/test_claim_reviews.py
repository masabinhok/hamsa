import httpx

from app.pipeline.claim_reviews import (
    MAX_REVIEWS,
    ClaimReviewSearch,
    add_reviews,
    parse,
    review_queries,
)
from app.pipeline.contracts import Evidence, SourceKind
from tests.factories import claim, passage

KEY = "test-key"

# Shape of a real claims:search response, trimmed.
RESPONSE = {
    "claims": [
        {
            "text": "Video shows flash flood in Nepal's Rasuwa district",
            "claimant": "Social media users",
            "claimDate": "2026-08-27T00:00:00Z",
            "claimReview": [
                {
                    "publisher": {"name": "AFP Fact Check", "site": "factcheck.afp.com"},
                    "url": "https://factcheck.afp.com/doc.afp.com.ABC",
                    "title": "Old Alaska glacier video falsely shared as Nepal flood",
                    "reviewDate": "2026-08-29T10:00:00Z",
                    "textualRating": "False",
                    "languageCode": "en",
                },
                {"publisher": {"name": "Broken"}, "url": "not a url"},
            ],
        }
    ]
}


def test_reviews_become_fact_check_passages() -> None:
    [review] = parse(RESPONSE)  # the review without a usable link is skipped
    assert review.source == "AFP Fact Check"
    assert review.source_kind is SourceKind.FACT_CHECK
    assert str(review.url) == "https://factcheck.afp.com/doc.afp.com.ABC"
    assert review.title == "Old Alaska glacier video falsely shared as Nepal flood"
    assert review.text == (
        'Fact-check of the claim "Video shows flash flood in Nepal\'s Rasuwa district" '
        "by Social media users (2026-08-27). Rating: False."
    )


def test_english_claim_and_on_screen_text_are_searched() -> None:
    queries = review_queries(claim(visible_text=["Columbia Glacier", "2019"]))
    assert queries == ["Melamchi bazaar was swept away", "Columbia Glacier 2019"]


def test_key_travels_in_a_header_never_in_the_url() -> None:
    seen: list[httpx.Request] = []

    def api(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=RESPONSE)

    search = ClaimReviewSearch(KEY, httpx.Client(transport=httpx.MockTransport(api)))
    reviews = search(claim(visible_text=["Columbia Glacier"]))

    assert len(reviews) == 1  # the same review from both queries counts once
    assert len(seen) == 2
    assert all(KEY not in str(r.url) for r in seen)
    assert seen[0].headers["X-Goog-Api-Key"] == KEY
    assert seen[0].url.params["query"] == "Melamchi bazaar was swept away"


def test_a_failing_search_returns_nothing_instead_of_failing_the_case() -> None:
    def api(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": {"message": "API key not valid"}})

    search = ClaimReviewSearch(KEY, httpx.Client(transport=httpx.MockTransport(api)))
    assert search(claim()) == []


def test_reviews_go_first_without_duplicates_and_evidence_stays_at_eight() -> None:
    corpus = [passage(f"p{n}", f"Outlet {n}") for n in range(8)]
    reviews = [
        passage("fc-a", "AFP", url="https://example.org/p0"),  # already in the corpus
        passage("fc-b", "Boom", source_kind="fact_check", url="https://boom.example/1"),
        passage("fc-c", "Alt News", source_kind="fact_check", url="https://alt.example/1"),
        passage("fc-d", "Newschecker", source_kind="fact_check", url="https://nc.example/1"),
    ]
    merged = add_reviews(Evidence(passages=corpus), reviews)
    ids = [p.passage_id for p in merged.passages]
    assert ids[:MAX_REVIEWS] == ["fc-b", "fc-c"]
    assert len(ids) == 8
    assert "p0" in ids
