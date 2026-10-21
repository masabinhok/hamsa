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
3. **Retrieves evidence.** bge-m3 cross-lingual search (Nepali ↔ English) over trusted news and official sources, plus fact-checks published abroad (AFP, Boom, Alt News and others) through Google's ClaimReview search when a key is set.
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
| Evidence retrieval | bge-m3 (Ollama, CPU per case; GPU for offline indexing) | `retrieve` in `backend/app/pipeline/retrieve.py`, and `WebSearch._passage` in `backend/app/pipeline/web_search.py` for web pages (cosine decides whether a page is evidence) → the passages the verdict model may cite; cited passages decide the "independent sources" and "conflict" rules in `backend/app/router/route.py` |
| Verdict | gpt-oss-120b (Groq); fallback Qwen3-VL-8B (local) | `judge` in `backend/app/pipeline/verdict.py` → label, confidence, and cited passages with stances decide the fast-track, conflict, and human-review rules in `backend/app/router/route.py`; the Nepali rationale is the published explanation |
| Fact-check relevance gate | gpt-oss-20b (Groq) | `same_claim_only` in `backend/app/pipeline/claim_reviews.py` → `SameClaim.same_claim` decides which published fact-checks enter the evidence; a kept one that agrees with the verdict can fast-track the case in `backend/app/router/route.py` |
| Rationale translation | gpt-oss-120b (Groq) | `translate` in `backend/app/pipeline/verdict.py`, served by `POST /desk/translate` in `backend/app/api/main.py` → the Nepali rationale a checker publishes after editing the English; checked by the row below before it is shown |
| Nepali rationale check | gpt-oss-20b (Groq) | `check_nepali` in `backend/app/pipeline/verdict.py` → `Verdict.nepali_issue`, and the `issue` the desk shows after a translation; any issue (or no check) is a conflict in `backend/app/router/route.py`, so the case goes to a checker instead of being fast-tracked |

## Running locally

**Setting Hamsa up for a fact-checking desk?** Follow [docs/install.md](docs/install.md): Ollama on the host, then `docker compose up -d --build` starts the API, worker, corpus watcher, website and vector store. The steps below are for developing Hamsa itself.

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com), an NVIDIA GPU with 8 GB VRAM (recommended), and a free [Groq](https://console.groq.com) API key (optional: without it, verdicts run on the local model).

```bash
docker compose up -d                          # Qdrant
ollama pull qwen3-vl:8b-instruct && ollama pull bge-m3
cp .env.example .env                          # set GROQ_API_KEY (and FETCH_BROWSER)

cd backend && uv sync
uv run python -m app.corpus fetch             # trusted articles, ~1 min
uv run python -m app.corpus index             # embed into Qdrant, ~15 min on the GPU
uv run python -m app.corpus watch             # keep it current: new articles every 15 min
uv run python -m app.archive                  # media archive from data/archive and eval originals

uv run python -m app.pipeline post.mp4 --text "caption"   # one post, end to end

uv run uvicorn --factory app.api.main:default_app         # API on :8000
uv run python -m app.worker                               # in a second terminal
uv run python -m app.telegram                             # optional: the Telegram bot (TELEGRAM_BOT_TOKEN)

cd ../frontend && npm install && npm run dev              # checker desk on :3000
```

Give each fact-checker an account: `uv run python -m app.checkers add "Sita Sharma"` prints her access code once (only its hash is stored); `list` and `remove` manage the rest. The desk asks only for the code, and the server records the checker's name on every decision. An optional `DESK_TOKEN` is the operator's key: it opens the desk too, but asks who is deciding. It talks to the API at `http://localhost:8000` unless `NEXT_PUBLIC_API_URL` is set in `frontend/.env.local`.

Submit a link with `curl -F "url=https://www.facebook.com/reel/..." localhost:8000/cases`: the worker downloads the post and its caption with the browser login named in `FETCH_BROWSER` (ADR 0010). Or submit files with `curl -F "text=..." -F "files=@post.mp4" localhost:8000/cases`; the checker desk API is under `/desk` with `Authorization: Bearer <access code>`. Interactive API docs: `localhost:8000/docs`.

## Evaluation

A labelled set of debunked and genuine posts from Nepal's 2026 disasters (`data/eval/`), labelled with each fact-checker's published rating. We report recycled-media precision and recall, verdict agreement (exact, and refuted-or-not), fast-track precision, the share sent to a human, and latency. A second run hides every fact-check from retrieval, to measure posts nobody has debunked yet.

```bash
cd backend
uv run python -m app.eval.score                    # tuning split, h001-h040
uv run python -m app.eval.score --no-fact-checks   # as if no fact-check existed
uv run python -m app.eval.score --split test       # held-out numbers for this README
```

Stage outputs are cached in `data/eval/runs/`, so rescoring after a threshold change reruns only the router.

## Limitations and future work

- Does not detect synthetic (AI-generated) media at the pixel level.
- Accuracy depends on how complete the archive is: brand-new footage can't be matched against anything.
- Reposts letterboxed with a blurred copy of the video (common on TikTok) are not yet matched; black bars, crops, mirroring, captions, and screenshots are ([measurements](docs/architecture.md#33-media-match-phash--siglip-cpu)).
- Nepali OCR on low-quality video frames is imperfect.
- Future work: a browser extension for newsrooms, more languages (Maithili, Bhojpuri), and a public verdict feed.

## Licence

MIT. See [LICENSE](LICENSE).
