# Hamsa (हंस)

*In our old stories, the hamsa (swan) can drink the milk from a mixture of milk and water and leave the water behind (नीर-क्षीर विवेक). Hamsa does the same for misinformation: it separates what's true from what's false.*

**An open-source fact-check triage desk for Nepali disaster misinformation, running entirely on open-weight AI.**

## The problem

After the August 26, 2026 flash floods in Nepal (900+ dead, thousands missing), social media filled with recycled and fabricated footage: clips from Uttarakhand and Alaska passed off as Nepal, fake "before/after" photos, and synthetic bridge-collapse videos. The Nepal Press Council's reporting portal received 101 complaints within days, and fact-checkers traced each one **by hand**.

Verification is slow because every claim repeats the same manual steps: figure out what is actually being claimed, check whether the media has appeared before, search for evidence, write a verdict. During a crisis, that delay is when misinformation does the most damage.

## What Hamsa does

A fact-checker (or a citizen, through a Telegram bot) submits a suspicious post, image, or video. Hamsa then:

1. **Extracts the claim.** Qwen3-VL reads the post and its frames and outputs structured JSON: claim, place, date claimed, numbers, and any watermarks or usernames visible in the frames.
2. **Checks whether the media is recycled.** Perceptual hashing catches exact reposts, and SigLIP embeddings catch crops and edits, both matched against an archive of past disaster footage from Nepal and abroad.
3. **Retrieves evidence.** bge-m3 cross-lingual search (Nepali ↔ English) over trusted news and official sources.
4. **Drafts a verdict.** gpt-oss-120b reasons over the evidence and returns a verdict, a confidence score, and citations as JSON.
5. **Routes the case.** The router acts on the AI's outputs: it auto-merges duplicate claims, fast-tracks high-confidence recycled media, sends ambiguous cases to a human checker with side-by-side evidence, and queues new claims for investigation.
6. **Keeps a human in charge.** Nothing is published without a checker's one-click approval.

**What we deliberately don't do:** pixel-level "is this AI-generated?" detection, which is unreliable. Hamsa focuses on deterministic, explainable signals: recycled media, contradicting evidence, and source provenance.

## Architecture

```
 Submission (web form / Telegram bot)
            │
            ▼
 ┌──────────────────────┐   keyframes (PyAV scene detect)
 │  Ingest & normalise  │──────────────────────────────┐
 └──────────┬───────────┘                              │
            ▼                                          ▼
 ┌──────────────────────┐              ┌─────────────────────────────┐
 │ Claim extraction     │              │ Media match                 │
 │ Qwen3-VL-8B → JSON   │              │ pHash + SigLIP → Qdrant     │
 └──────────┬───────────┘              └──────────────┬──────────────┘
            ▼                                         │
 ┌──────────────────────┐                             │
 │ Evidence retrieval   │  bge-m3 over trusted news   │
 └──────────┬───────────┘  (RSS + archive, Qdrant)    │
            ▼                                         │
 ┌──────────────────────┐                             │
 │ Verdict reasoning    │◄────────────────────────────┘
 │ gpt-oss-120b (Groq)  │  fallback: local Qwen3-8B
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐   merge dup │ fast-track │ human desk │ investigate
 │ Router               │──────────────────────────────────────────────────►
 └──────────┬───────────┘
            ▼
   Checker desk UI → one-click approve → published verdict
```

Detailed design: [`docs/architecture.md`](docs/architecture.md)

## Tech stack

| Layer | Choice | Licence / type |
|---|---|---|
| Vision + extraction | Qwen3-VL-8B via Ollama (local) | Open-weight (Apache 2.0) |
| Reasoning | gpt-oss-120b via Groq free tier; fallback Qwen3-8B local | Open-weight (Apache 2.0) |
| Text embeddings | bge-m3 | Open (MIT) |
| Image embeddings | SigLIP | Open (Apache 2.0) |
| Near-duplicate hashing | imagehash (pHash) | Open source |
| Vector DB | Qdrant (Docker) | Open source |
| Backend | Python, FastAPI | Open source |
| Frontend | Next.js | Open source |

**No proprietary AI APIs are used anywhere in the pipeline.**

## AI usage disclosure

*(Filled in with exact file and function names as the build progresses.)*

| AI step | Model | Where the output is consumed |
|---|---|---|
| Claim extraction | Qwen3-VL-8B | `backend/app/pipeline/extract.py` → JSON feeds retrieval queries and dedup |
| Media match | SigLIP | `backend/app/pipeline/media_match.py` → scores feed the router |
| Evidence retrieval | bge-m3 | `backend/app/pipeline/retrieve.py` → evidence passed to the reasoning step |
| Verdict | gpt-oss-120b | `backend/app/pipeline/verdict.py` → verdict and confidence drive `backend/app/router/route.py` |

## Running locally

*(Instructions coming in Week 2.)* Requirements: Python 3.11+, Docker, Ollama, an NVIDIA GPU with 8 GB+ VRAM (recommended), and a free Groq API key.

## Evaluation

A labelled set of known debunked items and genuine items from the August 2026 floods (`data/eval/`). We report recycled-media detection precision/recall and verdict agreement with published fact-checks.

## Limitations and future work

- Does not detect synthetic (AI-generated) media at the pixel level.
- Accuracy depends on how complete the archive is: brand-new footage can't be matched against anything.
- Nepali OCR on low-quality video frames is imperfect.
- Future work: a browser extension for newsrooms, more languages (Maithili, Bhojpuri), and a public verdict feed.

## Licence

MIT. See [LICENSE](LICENSE).
