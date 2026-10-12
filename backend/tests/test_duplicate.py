from collections.abc import Sequence

from app.pipeline.contracts import DuplicateBasis
from app.pipeline.duplicate import OpenClaim, claim_duplicate
from tests.factories import claim

# Stand-in for bge-m3: claims about the same event point the same way.
VECTORS = {
    "Melamchi bazaar was swept away": [1.0, 0.0, 0.0],
    "The flood swept Melamchi bazaar away": [0.98, 0.15, 0.0],
    "Melamchi hydropower intake was damaged": [0.6, 0.8, 0.0],
}


def embed(texts: Sequence[str]) -> list[list[float]]:
    return [VECTORS[t] for t in texts]


def open_claim(case_id: str, text: str, *places: str) -> OpenClaim:
    return OpenClaim(case_id, text, places)


def test_same_claim_about_the_same_place_is_a_duplicate() -> None:
    waiting = [open_claim("c1", "The flood swept Melamchi bazaar away", "melamchi")]
    duplicate = claim_duplicate(claim(), waiting, embed)
    assert duplicate is not None
    assert (duplicate.case_id, duplicate.basis) == ("c1", DuplicateBasis.CLAIM)


def test_a_different_claim_about_the_same_place_is_not() -> None:
    waiting = [open_claim("c1", "Melamchi hydropower intake was damaged", "Melamchi")]
    assert claim_duplicate(claim(), waiting, embed) is None


def test_no_shared_place_means_no_comparison() -> None:
    def unused(texts: Sequence[str]) -> list[list[float]]:
        raise AssertionError("nothing to compare, so nothing to embed")

    waiting = [open_claim("c1", "The flood swept Melamchi bazaar away", "Rasuwa")]
    assert claim_duplicate(claim(), waiting, unused) is None


def test_a_place_named_more_fully_still_overlaps() -> None:
    waiting = [open_claim("c1", "The flood swept Melamchi bazaar away", "मेलम्ची बजार")]
    duplicate = claim_duplicate(claim(places=["मेलम्ची"]), waiting, embed)
    assert duplicate is not None
