# Hamsa (हंस)

*In our old stories, the hamsa (swan) can drink the milk from a mixture of milk and water and leave the water behind (नीर-क्षीर विवेक). Hamsa does the same for misinformation: it separates what's true from what's false.*

**An open-source fact-check triage desk for Nepali disaster misinformation, running entirely on open-weight AI.**

## The problem

After the August 26, 2026 flash floods in Nepal (900+ dead, thousands missing), social media filled with recycled and fabricated footage: clips from Uttarakhand and Alaska passed off as Nepal, fake "before/after" photos, and synthetic bridge-collapse videos. The Nepal Press Council's reporting portal received 101 complaints within days, and fact-checkers traced each one **by hand**.

Verification is slow because every claim repeats the same manual steps: figure out what is actually being claimed, check whether the media has appeared before, search for evidence, write a verdict. During a crisis, that delay is when misinformation does the most damage.

## What Hamsa does

A fact-checker (or a citizen, through a Telegram or Messenger bot) submits a suspicious post, image, or video. Hamsa then:

1. **Extracts the claim.** Qwen3-VL reads the post and its frames and outputs structured JSON: claim, place, date claimed, numbers, and any watermarks or usernames visible in the frames.
2. **Checks whether the media is recycled.** Each keyframe is fingerprinted three ways and matched against Hamsa's archive of footage with a known origin. A perceptual hash (pHash) catches re-encodes, resizes and light crops. A SigLIP embedding catches the same scene under captions, overlays and heavier edits. ORB keypoints then prove geometrically that two frames are the same shot, not just a similar river. Mirrored frames are checked too.
3. **Retrieves evidence.** bge-m3 cross-lingual search (Nepali ↔ English) over trusted news and official sources, plus fact-checks published abroad (AFP, Boom, Alt News and others) through Google's ClaimReview search when a key is set.
4. **Drafts a verdict.** gpt-oss-120b reasons over the evidence and returns a verdict, a confidence score, and citations as JSON.
5. **Routes the case.** The router acts on the AI's outputs: it auto-merges duplicate claims, fast-tracks high-confidence recycled media, sends ambiguous cases to a human checker with side-by-side evidence, and queues new claims for investigation.
6. **Keeps a human in charge.** Nothing is published without a checker's one-click approval.

**It gets better with use.** Every verdict a checker publishes (true, false or misleading) is fingerprinted into the archive, and so is the original footage a checker finds by hand with the desk's Lens, Yandex and TinEye buttons. The next copy of that footage, even re-encoded, cropped or re-captioned, is recognised without anyone searching. An exact repeat (same link, post or file) is answered at once with the published verdict. Hamsa remembers; it does not retrain itself, so every decision stays auditable.

**How it scales.** The archive stores fingerprints, about 100 KB per keyframe, never the videos. Growth comes from use, and next from newsrooms sharing fingerprints and labels with each other, the way platforms share hashes of known harmful media ([ADR 0016](docs/adr/0016-scale-the-archive-by-sharing-fingerprints.md)).

**What it does not do:** search the web for every image automatically (there is no free reverse image search API, so the checker keeps one click), or recognise footage nobody has checked before (that goes to a human with news, fact-check and web evidence).

**What we deliberately don't do:** pixel-level "is this AI-generated?" detection, which is unreliable. Hamsa focuses on deterministic, explainable signals: recycled media, contradicting evidence, and source provenance.

## Architecture

```
 Submission (web form / Telegram / Messenger)
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

**No proprietary AI APIs are used anywhere in the pipeline.** The Frogtoberfest organisers confirmed that a hosted open-weight model (gpt-oss on Groq) is allowed. Without a Groq key, every call runs locally.

## AI usage disclosure

Every model call in Hamsa, and the code that acts on its output.

| AI step | Model | Where the output is consumed |
|---|---|---|
| Claim extraction | Qwen3-VL-8B (Ollama, local) | `extract_claim` in `backend/app/pipeline/extract.py` → `Claim` JSON: its text and places become retrieval queries and the dedup key; its `watermarks` and `checkable` fields drive rules in `backend/app/router/route.py` |
| Media match | SigLIP 2 (`google/siglip2-base-patch16-224`) | `match_media` in `backend/app/pipeline/media_match.py` → cosine scores, with pHash, decide `is_strong_match` in `backend/app/router/route.py`, which can fast-track a case as recycled media; `teach` in `backend/app/learn.py` embeds the footage of every published verdict into the archive the next post is matched against |
| Duplicate claims | bge-m3 (Ollama, CPU) | `claim_duplicate` in `backend/app/pipeline/duplicate.py` → cosine against open cases about the same place merges a new post into the case already on the desk |
| Evidence retrieval | bge-m3 (Ollama, CPU per case; GPU for offline indexing in `backend/app/corpus/__main__.py`) | `retrieve` in `backend/app/pipeline/retrieve.py`, and `WebSearch._passage` in `backend/app/pipeline/web_search.py` for web pages (cosine decides whether a page is evidence) → the passages the verdict model may cite; cited passages decide the "independent sources" and "conflict" rules in `backend/app/router/route.py` |
| Verdict | gpt-oss-120b (Groq); fallback Qwen3-VL-8B (local) | `judge` in `backend/app/pipeline/verdict.py` → label, confidence, and cited passages with stances decide the fast-track, conflict, and human-review rules in `backend/app/router/route.py`; the Nepali rationale is the published explanation |
| Fact-check relevance gate | gpt-oss-20b (Groq); offline: Qwen3-VL-8B (local) | `covering` in `backend/app/pipeline/claim_reviews.py` → `SameClaim.covers` decides which fact-checks, searched or from the corpus, enter the evidence; a kept one that agrees with the verdict can fast-track the case in `backend/app/router/route.py`; its recall is measured by `backend/app/eval/review_recall.py` |
| Rationale translation | gpt-oss-120b (Groq); offline: Qwen3-VL-8B (local), always marked "read every word" | `translate` in `backend/app/pipeline/verdict.py`, served by `POST /desk/translate` in `backend/app/api/main.py` → the Nepali rationale a checker publishes after editing the English; checked by the row below before it is shown |
| Nepali rationale check | gpt-oss-20b (Groq); offline: Qwen3-VL-8B (local) for verdicts | `check_nepali` in `backend/app/pipeline/verdict.py` → `Verdict.nepali_issue`, and the `issue` the desk shows after a translation; any issue (or no check) is a conflict in `backend/app/router/route.py`, so the case goes to a checker instead of being fast-tracked |

## Running locally

**Setting Hamsa up for a fact-checking desk?** Follow [docs/install.md](docs/install.md): Ollama on the host, then `docker compose up -d --build` starts the API, worker, corpus watcher, website and vector store. The steps below are for developing Hamsa itself.

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com), an NVIDIA GPU with 8 GB VRAM (recommended), and a free [Groq](https://console.groq.com) API key (optional: without it, every model call runs on the local Qwen3-VL and Hamsa works offline; every verdict then goes to a checker, since the fast-track rules were calibrated on gpt-oss).

```bash
cp .env.example .env && chmod 600 .env       # set SEARXNG_SECRET first (openssl rand -hex 32); GROQ_API_KEY, FETCH_BROWSER optional
docker compose up -d qdrant searxng           # the vector store and web search only
ollama pull qwen3-vl:8b-instruct && ollama pull bge-m3

cd backend && uv sync
uv run python -m app.corpus fetch             # trusted articles, ~1 min
uv run python -m app.corpus index             # embed into Qdrant, ~15 min on the GPU
uv run python -m app.corpus watch             # keep it current: new articles every 15 min
uv run python -m app.archive                  # rebuilds the media archive index (see below)

uv run python -m app.pipeline post.mp4 --text "caption"   # one post, end to end

uv run uvicorn --factory app.api.main:default_app         # API on :8000
uv run python -m app.worker                               # in a second terminal
uv run python -m app.telegram                             # optional: the Telegram bot (TELEGRAM_BOT_TOKEN)
uv run python -m app.messenger                            # optional: the Messenger bot (docs/install.md)

cd ../frontend && npm install && npm run dev              # checker desk on :3000
```

`app.archive` rebuilds the archive index from the clips in `data/archive/media/` and the eval originals. Those videos are other people's posts, so they are not in the repository: on a fresh clone the archive starts empty and grows from published verdicts (ADR 0011, 0014), or add clips with `python -m app.archive add <url>`. A rebuild re-reads every clip in `data/archive/manifest.csv`, learned ones included, so on a running desk it is safe, only slow.

Give each fact-checker an account: `uv run python -m app.checkers add "Sita Sharma"` prints her access code once (only its hash is stored); `list` and `remove` manage the rest. The desk asks only for the code, and the server records the checker's name on every decision. An optional `DESK_TOKEN` is the operator's key: it opens the desk too, but asks who is deciding. It talks to the API at `http://localhost:8000` unless `NEXT_PUBLIC_API_URL` is set in `frontend/.env.local`.

Submit a link with `curl -F "url=https://www.facebook.com/reel/..." localhost:8000/cases`: the worker downloads the post and its caption with the browser login named in `FETCH_BROWSER` (ADR 0010). Or submit files with `curl -F "text=..." -F "files=@post.mp4" localhost:8000/cases`; the checker desk API is under `/desk` with `Authorization: Bearer <access code>`. Interactive API docs: `localhost:8000/docs`.

## Evaluation

**Fast-track precision 8/8 on the tuning set, and 0 false posts cleared. The rest arrive on the desk drafted, with cited evidence.** Hamsa is deliberately conservative: it publishes nothing by itself, and 80% of posts go to a checker. The product is the evidence pack and the draft, not an automatic verdict.

Fresh run on 2026-10-24, on the code being submitted:

| Split | Items | Fast-track precision | Recycled media (precision, recall) | Refuted-or-not | Exact label | To a human | Latency p50 / p95 |
|---|---|---|---|---|---|---|---|
| Tuning (h001–h040) | 40 | 8/8 | 9/9, 9/13 | 31/40 | 21/40 | 31/40 | 46 s / 75 s |
| Held out (h041–h044) | 4 | none fast-tracked | –, 0/2 | 2/4 | 2/4 | 4/4 | 34 s / 44 s |

- **Exact label** is low partly by design: fact-checkers disagree on false versus misleading for the same pattern (Nepal Factcheck rates foreign footage passed off as Nepal "misleading", AFP rates it "false"). Refuted-or-not is what decides triage.
- **One unsafe route:** h030, a genuine Onlinekhabar clip of an APF inspector quoting a rescue ("we heard cries for help"), was dismissed as "not a checkable claim", so a true post never reached a checker. No false or misleading post was cleared.
- **The held-out split is small** (4 items). Read it with the live split below, which is real posts sent to Hamsa.

**Live split: 88 real posts sent to Hamsa as a reader would** (`data/eval/live/`, scored 2026-10-25 with `python -m app.eval.live`). The truth is the label a fact-checker published (or, for posts nobody had checked, the label the checker published on the desk).

| Posts | Items | Fast-track precision | Refuted-or-not | Exact label | To a human |
|---|---|---|---|---|---|
| Batches 01–02: rated by fact-checkers, genuine outlet footage, hard cases | 36 | 6/6 | 19/36 | 14/36 | 27/36 |
| Batches 03–04: mostly posts nobody had fact-checked | 52 | 1/1 | 38/52 | 31/52 | 51/52 |
| **All** | **88** | **7/7** | **57/88** | **45/88** | **78/88** |

- **Every fast-track on real posts was right (7 of 7).** Fast-track stays rare on purpose: 9 in 10 real posts go to a checker with the evidence attached.
- **Three rows are unsafe (L08–L10), all from batch 01:** a TikTok bug (fixed 2026-10-22) made blocked posts look like one file, so two merged and one was dismissed. Their stored outputs were rerouted through today's router, not rerun.
- **On posts nobody had checked, Hamsa's draft agreed with the checker's final label on 31 of 52 (60%)**, and on fake-or-not on 38 of 52 (73%). The checker changed the rest, which is what the desk is for.
- **Time saved was not measured** with a professional checker; see the latency above.
- **Time saved was not measured** with a professional checker. Latency is what Hamsa takes before a checker opens the case: under a minute for most posts, with the original footage, sources and a Nepali/English draft already attached.

A labelled set of debunked and genuine posts from Nepal's 2026 disasters (`data/eval/`), labelled with each fact-checker's published rating. We report recycled-media precision and recall, verdict agreement (exact, and refuted-or-not), fast-track precision, the share sent to a human, and latency. A second run hides every fact-check from retrieval, to measure posts nobody has debunked yet.

```bash
cd backend
uv run python -m app.eval.score                    # tuning split, h001-h040
uv run python -m app.eval.score --no-fact-checks   # as if no fact-check existed
uv run python -m app.eval.score --split test       # held-out numbers for this README
uv run python -m app.eval.live                     # real posts sent to Hamsa (data/eval/live/)
```

Stage outputs are cached in `data/eval/runs/`, so rescoring after a threshold change reruns only the router.

## Limitations and future work

- Does not detect synthetic (AI-generated) media at the pixel level.
- New footage nobody has checked can't be matched against anything, so it always reaches a human first; the archive grows with every published verdict and never has to be complete ([ADR 0014](docs/adr/0014-archive-is-a-memory-not-a-library.md)).
- Private, deleted or age-restricted posts can't be fetched from their link; the sender is asked for the photo or video, on Telegram or the report page, and it joins the same report.
- Reposts letterboxed with a blurred copy of the video (common on TikTok) are not yet matched; black bars, crops, mirroring, captions, and screenshots are ([measurements](docs/architecture.md#33-media-match-phash--siglip-cpu)).
- Nepali OCR on low-quality video frames is imperfect.
- Future work: topics beyond disasters (a corpus filter, prompt wording and a labelled set per topic, [ADR 0015](docs/adr/0015-disaster-scope-and-what-widening-it-takes.md)), a browser extension for newsrooms, more languages (Maithili, Bhojpuri), and a public verdict feed.

## Licence

MIT. See [LICENSE](LICENSE).
