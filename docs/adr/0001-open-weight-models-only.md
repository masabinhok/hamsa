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
- **Fully offline without a key (2026-10-23).** With no `GROQ_API_KEY`, every call runs on the local Qwen3-VL instead of being switched off: verdicts, the fact-check relevance gate, the Nepali check, and the desk's translation. Its verdicts count as fallbacks, so none is fast-tracked: the router's rules were calibrated on gpt-oss. Measured on the local model: the relevance gate dropped all 4 unrelated fact-checks on the genuine Sky News report and kept all 4 about the AI elephant video; the Nepali check caught a planted negation flip. Its translations garbled disaster words in 5 of 5 sentences (a flood became "an old man's exhibition") and its own check passed all 5, so the desk shows every local translation with "read every word" and does not check it with the same model.
- Groq is a hosted inference provider serving open-weight models on its free tier; no paid key is needed, and the product works without it.
