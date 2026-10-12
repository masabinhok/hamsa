"""Duplicate check (architecture 3.4): the same claim is already open on the desk.

Exact media duplicates are caught earlier, in the worker, by sha256 before any model runs.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from app.pipeline.contracts import Claim, Duplicate, DuplicateBasis

SAME_CLAIM_COSINE = 0.92  # starting value (architecture 3.4)

# Same shape as retrieve.EmbedText, kept here so the case store can import OpenClaim
# without loading the retrieval stack.
EmbedText = Callable[[Sequence[str]], list[list[float]]]


@dataclass(frozen=True)
class OpenClaim:
    case_id: str
    claim_en: str
    places: tuple[str, ...]


def claim_duplicate(
    claim: Claim, open_claims: Sequence[OpenClaim], embed: EmbedText
) -> Duplicate | None:
    """The open case making the same claim about the same place, if any.

    shortcut: places match by name, so "रसुवा" and "Rasuwa" do not overlap; normalise
    place names if eval data shows missed merges.
    """
    candidates = [c for c in open_claims if _share_a_place(claim.places, c.places)]
    if not candidates:
        return None
    vectors = np.asarray(embed([claim.claim_en, *(c.claim_en for c in candidates)]))
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    similarity = vectors[1:] @ vectors[0]
    best = int(np.argmax(similarity))
    if similarity[best] < SAME_CLAIM_COSINE:
        return None
    return Duplicate(case_id=candidates[best].case_id, basis=DuplicateBasis.CLAIM)


def _share_a_place(a: Sequence[str], b: Sequence[str]) -> bool:
    # One name inside the other: "बुटवल" and "बुटवल उपमहानगरपालिका" are the same place.
    return any(x in y or y in x for x in map(str.casefold, a) for y in map(str.casefold, b))
