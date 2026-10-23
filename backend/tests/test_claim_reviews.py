from collections.abc import Sequence

import httpx

from app.llm.structured import StructuredOutputError
from app.pipeline.claim_reviews import (
    MAX_REVIEWS,
    ClaimReviewSearch,
    add_reviews,
    covering,
    parse,
    review_queries,
    same_claim_only,
    vetted,
)
from app.pipeline.contracts import Claim, Evidence, Passage, SourceKind
from tests.factories import claim, passage
from tests.test_verdict import FakeReasoner

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
    # The claim has 5 words, so its 12-, 8- and 5-word queries are one.
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


def test_long_claims_are_searched_by_their_opening_words() -> None:
    long_claim = "one two three four five six seven eight nine ten eleven twelve thirteen"
    assert review_queries(claim(claim_en=long_claim)) == [
        "one two three four five six seven eight nine ten eleven twelve",
        "one two three four five six seven eight",
        "one two three four five",
    ]


def test_a_review_found_by_several_queries_ranks_first() -> None:
    def review(n: int) -> dict[str, object]:
        return {"publisher": {"name": f"P{n}"}, "url": f"https://fc.example/{n}"}

    # Review 2 is second for every query; review 1 tops only the first.
    pages = {
        "one two three four five six seven eight nine ten eleven twelve": [1, 2],
        "one two three four five six seven eight": [3, 2],
        "one two three four five": [4, 2],
    }

    def api(request: httpx.Request) -> httpx.Response:
        found = pages[request.url.params["query"]]
        return httpx.Response(
            200, json={"claims": [{"text": "x", "claimReview": [review(n) for n in found]}]}
        )

    search = ClaimReviewSearch(KEY, httpx.Client(transport=httpx.MockTransport(api)))
    words = "one two three four five six seven eight nine ten eleven twelve thirteen"
    ranked = [str(p.url) for p in search(claim(claim_en=words))]
    assert ranked[0] == "https://fc.example/2"
    assert sorted(ranked) == [f"https://fc.example/{n}" for n in (1, 2, 3, 4)]


def test_only_reviews_judged_about_this_post_are_kept() -> None:
    found = [passage(f"fc-{n}", f"Checker {n}", source_kind="fact_check") for n in range(6)]

    def search(_: Claim) -> list[Passage]:
        return found

    def site(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fc-0":
            return httpx.Response(403)  # judged on its headline alone
        return httpx.Response(200, text="<p>The video of the Columbia Glacier</p>")

    judge = FakeReasoner(
        answer(False, "a roundup of other flood videos"),
        StructuredOutputError("no json"),  # unjudged: dropped, never let through
        answer(True, "a glacier collapsing", fits=True),
        answer(True, "not described"),  # a claim about a cause, not a video
    )
    http = httpx.Client(transport=httpx.MockTransport(site))
    vet = covering((judge, "gate-model"), http)
    kept = same_claim_only(search, vet)(claim(visible_text=["Juneau"]))

    assert [p.source for p in kept] == ["Checker 2", "Checker 3"]
    assert len(judge.prompts) == MAX_REVIEWS + 2  # stops once the evidence slots are full
    assert "Juneau" in judge.prompts[0]
    assert "Article:" not in judge.prompts[0]
    assert "Columbia Glacier" in judge.prompts[2]


def answer(same: bool, footage: str, *, fits: bool = False) -> dict[str, object]:
    return {
        "checked_footage": footage,
        "footage_fits_scene": fits,
        "same_claim": same,
        "why": "",
    }


def test_a_fact_check_of_other_footage_never_covers_a_post_that_shows_footage() -> None:
    from app.pipeline.claim_reviews import SameClaim

    sky = claim(scene="a reporter by a muddy river, then officials at a table")
    other = SameClaim.model_validate(answer(True, "an old video from Pakistan"))
    assert not other.covers(sky)  # the Sky News report, drafted false on this
    assert other.covers(claim())  # a text post has no footage to differ
    assert SameClaim.model_validate(answer(True, "not described")).covers(sky)


def test_corpus_fact_checks_are_vetted_and_news_is_left_alone() -> None:
    other = passage("c1", "Nepal Factcheck", source_kind=SourceKind.FACT_CHECK)
    right = passage("c2", "AFP Fact Check", source_kind=SourceKind.FACT_CHECK)
    news = passage("n1", "Onlinekhabar")
    evidence = Evidence(passages=[other, news, right])
    seen: list[Passage] = []

    def vet(_: Claim, reviews: Sequence[Passage], enough: int | None) -> list[Passage]:
        seen.extend(reviews)
        return [right]

    kept = vetted(claim(), evidence, vet)
    assert [p.passage_id for p in kept.passages] == ["n1", "c2"]
    assert seen == [other, right]  # news never reaches the judge
    assert vetted(claim(), evidence, None) is evidence
