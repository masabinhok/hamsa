# 0001. Open-weight models only, reasoning on Groq with a local fallback

- Status: Accepted
- Date: 2026-10-06

## Context
Frogtoberfest requires open-source or open-weight AI end to end and discourages proprietary APIs even for small calls. Beyond the rules, the users are Nepali newsrooms and fact-checkers who cannot depend on a paid foreign API for a public-interest tool, and who may need to run it themselves during a disaster when budgets and connectivity are both thin.

## Options considered
- **Everything local.** No cost, works offline. But the best reasoning model that fits on 8 GB is about 8B parameters, which is noticeably weaker at weighing conflicting evidence.
- **Everything on a hosted open-weight provider.** Strong models, but the whole product stops when the free tier rate-limits or the network drops.
- **Hosted for reasoning, local for everything else, local fallback for reasoning.**

## Decision
Run reasoning on gpt-oss-120b via Groq's free tier. Run vision, extraction, and embeddings locally. If Groq is unavailable, rate-limited, or not configured, the verdict step falls back to the local vision model.

## Consequences
- The verdict quality depends on Groq being reachable. The fallback is weaker, so every verdict records which model produced it, and the desk shows it.
- Groq free-tier limits cap throughput. That is fine at desk scale but must be handled with retries and backoff.
- Nothing proprietary in the repo, including scripts and evals.
