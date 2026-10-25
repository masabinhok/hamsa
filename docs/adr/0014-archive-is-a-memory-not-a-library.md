# 0014. The archive is a memory of checked footage, not a library that must be complete

- Status: Accepted
- Date: 2026-10-23

## Context
After a week of real posts the question was whether Hamsa needs its archive at all: it held a few dozen clips, so a partial archive seemed likely to mislead the model, and a newsroom like Techpana would need years of disaster footage to make it complete. The fear was grounded. A recent Budhi Gandaki flood was drafted false at 0.97 from a weak archive hit, and a real flood video "matched" three 2015 earthquake clips through a black frame.

## Options considered
- **Drop the archive** and rely on news and fact-checks. Rejected: on the tuning split, every recycled-media fast-track rests on it (9 of 9 correct, recall 9 of 13), and no news report or fact-check exists for a repost nobody has written about. It is also the only way Hamsa recognises footage it has already checked (below).
- **Make it complete**: bulk-download past disasters. Rejected in [ADR 0011](0011-archive-learns-from-verdicts.md): unbounded storage, and it misses what goes viral next.
- **Keep it partial, and make a partial archive safe.** The harm came from weak matches and blank frames reaching the model, not from the archive being small.

## Decision
The archive is Hamsa's memory of footage someone has checked, seeded with a few dozen well-documented clips and grown by every published verdict (ADR 0011). It never has to be complete, because a miss costs nothing: with no strong match the case is judged on news, fact-checks and the web, as it would be without an archive. What it must never do is mislead, so:
- only strong matches (pHash, SigLIP or ORB above their thresholds) reach the verdict model (`d3ef9cb`);
- blank frames are never keyframes (`dbf8ec6`);
- footage the post itself dates correctly is not "recycled" (`50a6465`);
- a fact-check or report never stands in for a frame match on footage (`53dc263`, `dff577d`).

A newsroom adopting Hamsa can seed the archive with its own past footage (`python -m app.archive add`), but it does not need to.

## Consequences
- New footage nobody has checked always reaches a human first; every later copy is caught. Measured 2026-10-23: re-encoded copies (CRF 35, 5% crop, 480p) of a published true clip and a published false clip were fast-tracked with the checker's label ("same footage published as … on Hamsa"), and the true clip re-captioned as a new flood was not.
- Recall on recycled footage is bounded by what has been checked, so it is reported separately from precision in the eval.
