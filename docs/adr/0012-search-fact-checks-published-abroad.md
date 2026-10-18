# 0012. Search fact-checks published abroad through ClaimReview, not by crawling each fact-checker

- Status: Accepted
- Date: 2026-10-18

## Context
The evidence corpus holds fact-checks from two Nepali sources, Nepal Factcheck and Techpana. But of the 33 eval posts labelled from a fact-check, 22 were debunked by fact-checkers abroad: AFP, Boom, Alt News, CyberPeace, Newschecker, AAP, Lead Stories and Fact Crescendo. A viral fake about a Nepali disaster is usually debunked in India or by AFP first, so Hamsa missed the strongest evidence for most posts that were not already in its archive.

## Options considered
- **Add each fact-checker to the corpus.** One RSS or WordPress source per outlet, as for the Nepali ones. Rejected: about ten outlets in several languages, several block automated access, and their feeds cover every topic, so the disaster-term filter would also drop debunks of Nepal footage that never say "flood".
- **Web search per case.** Rejected for the same reasons as in ADR 0011: no free search API, and results need a model to sort.
- **Google Fact Check Tools API.** Most fact-checkers mark their articles with ClaimReview (claim, rating, publisher), and this free API searches that index. It is a search service, not a model, so the open-weight rule (ADR 0001) is unaffected.

## Decision
When `FACT_CHECK_API_KEY` is set, the retrieval stage searches ClaimReview with the English claim and the on-screen text (`backend/app/pipeline/claim_reviews.py`). Up to 2 reviews not already in the corpus become `fact_check` passages placed ahead of the corpus passages, in the same 8 slots. The verdict model and the router's "prior fact-check agrees" rule then treat them like any other fact-check. The key travels in a header, never in a logged URL. A failed search leaves the case with corpus evidence only.

## Consequences
- The English claim text of each case is sent to Google when a key is set. Without a key, nothing changes.
- A loosely related review (another flood, another video) can reach the verdict model. The prompt already says to decide only on evidence about this claim, and the router still needs high confidence and no conflict to fast-track.
- `python -m app.eval.score --no-fact-checks` turns the search off, so that run still measures posts nobody has debunked.
- How often the search finds the right fact-check is measured by `python -m app.eval.review_recall`, which has to run with a key before any number is claimed.
