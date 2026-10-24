# Architecture decision records

One file per decision that had a real alternative. A record is never edited after it is accepted. A changed decision gets a new record, and the old one is marked `Superseded by NNNN`.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-open-weight-models-only.md) | Open-weight models only, reasoning on Groq with a local fallback | Accepted |
| [0002](0002-no-pixel-level-synthetic-detection.md) | No pixel-level AI-image detection; use provenance and evidence | Accepted |
| [0003](0003-two-tier-media-matching.md) | Two-tier media matching: pHash, then SigLIP | Accepted |
| [0004](0004-deterministic-router.md) | Models propose, a deterministic router decides, a human approves | Accepted |
| [0005](0005-sqlite-case-store-and-job-queue.md) | SQLite for cases and the job queue, one worker | Accepted |
| [0006](0006-direct-model-calls-no-framework.md) | Direct model calls with schema-validated JSON, no LLM framework | Accepted |
| [0007](0007-gpu-for-vision-model-only.md) | GPU reserved for the vision model; embedders on CPU | Accepted |
| [0008](0008-qdrant-vector-store.md) | Qdrant as the vector store | Accepted |
| [0009](0009-orb-geometric-verification.md) | ORB keypoints verify media matches geometrically | Accepted |
| [0010](0010-fetch-links-with-the-operators-browser-session.md) | Fetch pasted links with the operator's browser session | Accepted |
| [0011](0011-archive-learns-from-verdicts.md) | The archive learns from verdicts, not from bulk downloads or web search | Accepted |
| [0012](0012-search-fact-checks-published-abroad.md) | Search fact-checks published abroad through ClaimReview | Accepted |
| [0013](0013-web-evidence-through-self-hosted-searxng.md) | Search the web for evidence about the event through self-hosted SearXNG | Accepted |
| [0014](0014-archive-is-a-memory-not-a-library.md) | The archive is a memory of checked footage, not a library that must be complete | Accepted |
| [0015](0015-disaster-scope-and-what-widening-it-takes.md) | Stay scoped to disasters; widening is a corpus and prompt change | Accepted |
| [0016](0016-scale-the-archive-by-sharing-fingerprints.md) | Scale the archive by sharing fingerprints between desks, not storing media | Accepted (direction) |

Template: Status, Date, Context, Options considered, Decision, Consequences.
