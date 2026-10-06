# Hamsa (हंस)

*In our old stories, the hamsa (swan) can drink the milk from a mixture of milk and water and leave the water behind (नीर-क्षीर विवेक). Hamsa does the same for misinformation: it separates what's true from what's false.*

**An open-source fact-check triage desk for Nepali disaster misinformation, running entirely on open-weight AI.**

## The problem

After the August 26, 2026 flash floods in Nepal (900+ dead, thousands missing), social media filled with recycled and fabricated footage: clips from Uttarakhand and Alaska passed off as Nepal, fake "before/after" photos, and synthetic bridge-collapse videos. The Nepal Press Council's reporting portal received 101 complaints within days, and fact-checkers traced each one **by hand**.

Verification is slow because every claim repeats the same manual steps: figure out what is actually being claimed, check whether the media has appeared before, search for evidence, write a verdict. During a crisis, that delay is when misinformation does the most damage.

## What Hamsa does

A fact-checker (or a citizen, through a Telegram bot) submits a suspicious post, image, or video. Hamsa then:

1. **Extracts the claim.** Qwen3-VL reads the post and its frames and outputs structured JSON: claim, place, date claimed, numbers, and any watermarks or usernames visible in the frames.
2. **Checks whether the media is recycled.** Perceptual hashing catches reposts even when re-encoded, mirrored, letterboxed, or captioned, and SigLIP embeddings catch heavier crops, both matched against an archive of past disaster footage from Nepal and abroad.
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
 │ gpt-oss-120b (Groq)  │  fallback: local Qwen3-VL-8B
 └──────────┬───────────┘
            ▼
 ┌──────────────────────┐   merge dup │ fast-track │ human desk │ investigate
 │ Router               │──────────────────────────────────────────────────►
 └──────────┬───────────┘
            ▼
   Checker desk UI → one-click approve → published verdict
```

Detailed design: [`docs/architecture.md`](docs/architecture.md). Decisions and their trade-offs: [`docs/adr/`](docs/adr/).

## Tech stack

| Layer | Choice | Licence / type |
|---|---|---|
| Vision + extraction | Qwen3-VL-8B via Ollama (local) | Open-weight (Apache 2.0) |
| Reasoning | gpt-oss-120b via Groq free tier; fallback Qwen3-VL-8B local | Open-weight (Apache 2.0) |
| Text embeddings | bge-m3 | Open (MIT) |
| Image embeddings | SigLIP 2 base | Open (Apache 2.0) |
| Near-duplicate hashing | imagehash (pHash) | Open source |
| Vector DB | Qdrant (Docker) | Open source |
| Backend | Python, FastAPI | Open source |
| Frontend | Next.js | Open source |

**No proprietary AI APIs are used anywhere in the pipeline.**

## AI usage disclosure

*(Filled in with exact file and function names as the build progresses.)*

| AI step | Model | Where the output is consumed |
|---|---|---|
| Claim extraction | Qwen3-VL-8B (Ollama, local) | `extract_claim` in `backend/app/pipeline/extract.py` → `Claim` JSON: its text and places become retrieval queries and the dedup key; its `watermarks` and `checkable` fields drive rules in `backend/app/router/route.py` |
| Media match | SigLIP 2 (`google/siglip2-base-patch16-224`) | `match_media` in `backend/app/pipeline/media_match.py` → cosine scores, with pHash, decide `is_strong_match` in `backend/app/router/route.py`, which can fast-track a case as recycled media |
| Evidence retrieval | bge-m3 (Ollama, CPU per case; GPU for offline indexing) | `retrieve` in `backend/app/pipeline/retrieve.py` → the passages the verdict model may cite; cited passages decide the "independent sources" and "conflict" rules in `backend/app/router/route.py` |
| Verdict | gpt-oss-120b (Groq); fallback Qwen3-VL-8B (local) | `judge` in `backend/app/pipeline/verdict.py` → label, confidence, and cited passages with stances decide the fast-track, conflict, and human-review rules in `backend/app/router/route.py`; the Nepali rationale is the published explanation |

## Running locally

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com), an NVIDIA GPU with 8 GB VRAM (recommended), and a free [Groq](https://console.groq.com) API key (optional: without it, verdicts run on the local model).

```bash
docker compose up -d                          # Qdrant
ollama pull qwen3-vl:8b-instruct && ollama pull bge-m3
cp .env.example .env                          # set GROQ_API_KEY and DESK_TOKEN

cd backend && uv sync
uv run python -m app.corpus fetch             # trusted articles, ~1 min
uv run python -m app.corpus index             # embed into Qdrant, ~15 min on the GPU
uv run python -m app.archive                  # media archive from data/archive and eval originals

uv run python -m app.pipeline post.mp4 --text "caption"   # one post, end to end

uv run uvicorn --factory app.api.main:default_app         # API on :8000
uv run python -m app.worker                               # in a second terminal
```

Submit with `curl -F "text=..." -F "files=@post.mp4" localhost:8000/cases`; the checker desk API is under `/desk` with `Authorization: Bearer $DESK_TOKEN`. Interactive API docs: `localhost:8000/docs`.

## Evaluation

A labelled set of known debunked items and genuine items from the August 2026 floods (`data/eval/`). We report recycled-media detection precision/recall and verdict agreement with published fact-checks.

## Limitations and future work

- Does not detect synthetic (AI-generated) media at the pixel level.
- Accuracy depends on how complete the archive is: brand-new footage can't be matched against anything.
- Reposts letterboxed with a blurred copy of the video (common on TikTok) are not yet matched; black bars, crops, mirroring, captions, and screenshots are ([measurements](docs/architecture.md#33-media-match-phash--siglip-cpu)).
- Nepali OCR on low-quality video frames is imperfect.
- Future work: a browser extension for newsrooms, more languages (Maithili, Bhojpuri), and a public verdict feed.

## Licence

MIT. See [LICENSE](LICENSE).
