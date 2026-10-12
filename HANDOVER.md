# Handover

State of Hamsa as of 2026-10-11. Read with `README.md`, `CLAUDE.md`, `docs/architecture.md`, and `docs/adr/`.

## Project

- Hamsa: a fact-check triage desk for Nepali disaster misinformation (the August 2026 floods first, now any Nepal disaster), using open-weight models only.
- Solo entry to Leapfrog's Frogtoberfest 2026. Demo day is **Oct 30, 2026** in Kathmandu.
- Eligibility needs a public repo, a working demo, a demo video, and docs (README, architecture, tech details, limitations).
- The idea lock-in form is submitted. Its answers describe the plan, not the build.

## Repository state

- Work happens on **`develop`**; `main` holds releases. Both were first pushed on 2026-10-11 (`main` = `develop` at that point).
- Push only when the owner says so.
- Every merged branch passed ruff, pyright (strict), and pytest (183 tests). The frontend passes tsc and eslint.

## What is built

| Part | Where | Run |
|---|---|---|
| Claim extraction (Qwen3-VL-8B via Ollama) | `backend/app/pipeline/extract.py` | `uv run python -m app.pipeline.extract post.mp4 --text "..."` |
| Media match (pHash + SigLIP 2, Qdrant) | `backend/app/pipeline/media_match.py` | thresholds measured by `uv run python -m app.eval.media_robustness` |
| Evidence corpus and retrieval (bge-m3) | `backend/app/corpus/`, `backend/app/pipeline/retrieve.py` | `uv run python -m app.corpus fetch`, then `... index` (about 15 min on the GPU) |
| Verdict (gpt-oss-120b on Groq, local fallback) | `backend/app/pipeline/verdict.py`, `backend/app/llm/` | needs `GROQ_API_KEY` in `.env` |
| Deterministic router | `backend/app/router/route.py` | pure function, see architecture section 3.7 |
| Whole pipeline, one post | `backend/app/pipeline/run.py` | `uv run python -m app.pipeline post.mp4 --text "..."` |
| Case store, job queue, worker | `backend/app/store/`, `backend/app/worker.py` | `uv run python -m app.worker` |
| HTTP API (public plus checker desk) | `backend/app/api/` | `uv run uvicorn --factory app.api.main:default_app` |
| Media archive build and collector | `backend/app/archive.py` | `uv run python -m app.archive`; add a clip with `... add <url> --label verified_genuine --context "..."` |
| Eval dataset schema and validator | `backend/app/eval/dataset.py` | `uv run python -m app.eval.validate` |
| Eval scorer | `backend/app/eval/score.py` | `uv run python -m app.eval.score [--split tune\|test] [--no-fact-checks]`; results cached in `data/eval/runs/` |
| Checker desk UI (Next.js 16) | `frontend/src/` | `npm run dev`, then sign in with your name and `DESK_TOKEN` |

- Setup steps are in the README under "Running locally". Run the backend commands from `backend/`.
- Qdrant runs in Docker (`docker compose up -d`). The evidence corpus is indexed: 5,626 articles, 15,806 passages (fetched 2026-10-11).
- The media archive holds 37 news clips from `data/archive/manifest.csv` plus the originals of recycled eval items. Rebuild with `uv run python -m app.archive` after adding either.
- A genuine archive clip dated more than 30 days before a post counts as recycled (`same_event_days` in the router).

## Measured so far

- **Eval tuning split (29 items, h001-h040), 2026-10-12, with ORB matching and the extraction fixes:** fast-track precision 9/9, recycled media precision 6/6 and recall 6/9, refuted-or-not agreement 24/29, exact verdict agreement 14/29, 20/29 sent to a human, latency p50 35 s and p95 72 s. No unsafe routes. Reports in `data/eval/runs/default/`.

- **Real Rasuwa viral post:** extract, match, retrieve, verdict, then `fast_track` ("prior fact-check agrees: Nepal Factcheck"). The verdict was `false` 0.92 and named the Alaska origin. About 17.5 s warm.
- **Invented Melamchi claim:** `unverifiable`, sent to `human_review`.
- **Media robustness:** 17 of 20 edited reposts matched, with 0 false matches on 5 same-river hard negatives. Blurred-background letterboxes are missed.
- **Full service smoke test:** submit through the API, the worker routes it, publish one-click in the desk, the public verdict appears. This passed in a headless browser.

## Eval data

- `data/eval/items.csv`: 33 verified rows, committed 2026-10-11 (false 16, true 10, misleading 7; recycled 11, synthetic 9). h001-h040 tune, h041 onward is held out.
- `data/eval/drafts.csv`: the rest of the 50 drafts (h011-h060), gitignored. 16 still need media by hand, listed in `data/eval/drafts-report.md`. h050 has no original link.
- **Label rule:** follow each fact-checker's published rating (`docs/data-collection.md`). The scorer also reports refuted-or-not.
- **Never take media from a fact-check article.** Crosses and "FALSE" stamps leak the label.
- **Never archive an eval post.** `app.archive add` refuses them, and the build prints `check:` lines for near matches.
- **Still to find:** unverifiable posts (only h059 so far).

## Next steps, in order

Built since 2026-10-11: ORB media verification (ADR 0009), the desk's side-by-side archive view and copy-frame reverse search, the public submit page (`/`) and report page (`/check/{id}`), the Nepali rationale check (gpt-oss-20b), and duplicate merging (identical file, or same claim and place).

1. **More eval rows** (owner), so the held-out split (h041 onward, 4 rows now) reaches at least 10.
2. **Full fresh eval run** (`uv run python -m app.eval.score --fresh`), now that verdicts carry the Nepali check, then held-out numbers in the README.
3. **Demo video**, then the final AI disclosure check and a release merge to `main`.

Known misses: h005/h006 (the "original" is a different shot), h007 (news template). The local `data/hamsa.db` holds test cases from end-to-end checks; delete it for a clean demo.

## Known limits and gotchas

- **Groq free tier:** 8,000 tokens/min, roughly 2 verdicts per minute. The client waits out `retry-after` up to 30 s, then falls back.
- **Verdicts vary between runs** even at temperature 0. The router thresholds absorb this, so tune them on eval data.
- **The local fallback verdict is weaker.** It is flagged as `fallback`, and the router never fast-tracks it on judgement alone.
- **The vision model does not fully fit in 8 GB VRAM** (about 29% spills to the CPU). Do not raise `num_ctx` past 8192.
- **yt-dlp downloads:**
  - Facebook, TikTok and X work with `--cookies-from-browser firefox`.
  - YouTube fails *with* browser cookies ("page needs to be reloaded"): download it without them.
  - Some Facebook reels fail with "Cannot parse data", and Facebook photos are unsupported: save those by hand.
- **Never commit while a background job writes a tracked file:** pre-commit rolls the file back to its stash and the job's writes are lost (this happened to `manifest.csv`).
- **Pre-commit leaves untracked files on disk,** so pyright can check a tree that will not exist. Commit in dependency order, never hide commit output, and check each commit landed (see `CLAUDE.md`).
- **Shell:** zsh does not word-split `$var`, and `pkill -f <pattern>` can kill its own shell. Stop services by PID.
- `graphify-out/` (a code knowledge graph) is generated and gitignored.
