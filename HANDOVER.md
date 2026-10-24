# Handover

State of Hamsa as of 2026-10-24. Read with `README.md`, `CLAUDE.md`, `docs/architecture.md`, `docs/adr/`, `docs/demo.md`, and `ISSUES.md`.

## Project

- Hamsa: a fact-check triage desk for Nepali disaster misinformation (any Nepal disaster), using open-weight models only.
- Solo entry to Leapfrog's Frogtoberfest 2026. **Final submission Oct 25**, demo day **Oct 30, 2026** in Kathmandu.
- Eligibility needs a public repo, a working demo, a demo video, and docs (README, architecture, tech details, limitations).
- Judged on impact and quality. Quality is strong (ADRs, tests, measured decisions, a deterministic router). Impact is credible but unproven: nobody besides the owner has used it yet, and no time saving has been measured.

## Repository state

- Work happens on **`develop`**; `main` holds releases (last release merge `639317c`). Push only when the owner says so.
- Every merged branch passed ruff, pyright (strict), and pytest (316 tests). The frontend passes tsc and eslint.
- `ISSUES.md` holds the Oct field-test findings and ideas, with a proposed order of work at the end.

## What is built

| Part | Where | Run |
|---|---|---|
| Claim extraction (Qwen3-VL-8B via Ollama) | `backend/app/pipeline/extract.py` | `uv run python -m app.pipeline.extract post.mp4 --text "..."` |
| Media match (pHash + SigLIP 2 + ORB, Qdrant) | `backend/app/pipeline/media_match.py` | thresholds measured by `uv run python -m app.eval.media_robustness` |
| Evidence: corpus (bge-m3), fact-checks abroad (ClaimReview), web (self-hosted SearXNG) | `backend/app/corpus/`, `backend/app/pipeline/retrieve.py`, `claim_reviews.py`, `web_search.py` | `uv run python -m app.corpus fetch`, `... index`, `... watch` |
| Verdict (gpt-oss-120b on Groq; local Qwen3-VL without a key) | `backend/app/pipeline/verdict.py`, `backend/app/llm/` | `GROQ_API_KEY` in `.env` is optional; without it every call is local and every case goes to a checker |
| Deterministic router | `backend/app/router/route.py` | pure function, see architecture section 3.7 |
| Whole pipeline, one post | `backend/app/pipeline/run.py` | `uv run python -m app.pipeline post.mp4 --text "..."` |
| Case store, job queue, worker | `backend/app/store/`, `backend/app/worker.py` | `uv run python -m app.worker` |
| Repeat posts | `backend/app/worker.py`, `post_ids` table | a repost (same link, platform post id, or file) merges before any model runs; a decided report answers at once |
| HTTP API (public plus checker desk) | `backend/app/api/` | `uv run uvicorn --factory app.api.main:default_app` |
| Telegram bot | `backend/app/telegram.py` | `uv run python -m app.telegram` (`TELEGRAM_BOT_TOKEN`) |
| Messenger page | `backend/app/messenger.py` | webhook on port 8001 behind cloudflared; works for page admins and testers without app review (`docs/install.md`) |
| Media archive, learns from published verdicts | `backend/app/archive.py` | `uv run python -m app.archive`; add a clip with `... add <url> --label verified_genuine --context "..."` |
| Eval scorer (tune/test) and live split | `backend/app/eval/score.py`, `backend/app/eval/live.py` | `uv run python -m app.eval.score [--split tune\|test] [--fresh]`, `uv run python -m app.eval.live [--fresh]` |
| Public site and checker desk (Next.js 16) | `frontend/src/` | `npm run dev`; add checkers with `uv run python -m app.checkers add NAME` |
| Whole stack | `docker-compose.yml` | `docker compose up -d --build` (add `--profile telegram` or `--profile messenger` for the bots), see `docs/install.md` |

- Setup steps are in the README under "Running locally". Run the backend commands from `backend/`.
- The desk drafts Nepali from the checker's English; an edited English rationale redoes the Nepali when the box loses focus, and publishing waits for it.

## Measured so far

Reports from 2026-10-23 (before the fully-local merge, which only changes the no-key path):

- **Tune split (40 items, h001-h040):** fast-track precision 7/7, recycled media precision 9/9 and recall 9/13, refuted-or-not 33/40, exact 22/40, 33/40 sent to a human, latency p50 52 s, p95 169 s. `data/eval/runs/default/report-tune.md`.
- **Held-out split (4 items, h041-h044):** fast-track 1/1, exact 2/4, 3/4 to a human. Too small to quote alone.
- **Live split (32 real posts sent to Hamsa, `data/eval/live/batch-01.md`, `batch-02.md`):** fast-track 6/6, exact 11/32, refuted-or-not 16/32, 23/32 to a human. The 3 unsafe rows are the TikTok landing-page bug fixed in `956451a`; stored outputs were rerouted, not rerun. `data/eval/runs/live/report.md`.
- **How to frame the numbers:** the product is the evidence pack and the draft, and fast-track is deliberately conservative. Lead with "fast-track precision X/Y; the rest arrive drafted with cited evidence".
- **Media robustness:** 17 of 20 edited reposts matched, with 0 false matches on 5 same-river hard negatives. Blurred-background letterboxes are missed.

## Eval data

- `data/eval/items.csv`: 44 rows. h001-h040 tune, h041 onward held out.
- `data/eval/live/batch-*.md`: real posts with the source of each expected label. A label a checker publishes overrides the row's expected one.
- **Label rule:** follow each fact-checker's published rating (`docs/data-collection.md`). The scorer also reports refuted-or-not.
- **Never take media from a fact-check article.** Crosses and "FALSE" stamps leak the label.
- **Never archive an eval post.** `app.archive add` refuses them, and the build prints `check:` lines for near matches.

## Next steps, in order (for the Oct 25 submission)

1. **Fresh evals on today's code:** `uv run python -m app.eval.score --split tune --fresh` and `uv run python -m app.eval.live --fresh`, then lead the README's Evaluation section with the numbers. Fresh runs pace themselves to Groq's limit (a minute per item). Stop the live stack first (see gotchas).
2. **One real fact-checker** (Nepal Factcheck, Newschecker Nepal, or a journalist) tries it for 15 minutes; a quote and their numbers go in the README.
3. **Measure time saved:** check 5 posts by hand (timed), then the same 5 with Hamsa's evidence pack.
4. **Record the demo** from `docs/demo.md` on a clean demo database, so Oct 30 can fall back to the recording.
5. **Groq:** get the organisers' written answer on whether a hosted open-weight model is allowed. Offline mode exists if not.
6. **Release:** AI usage disclosure check in the README, then merge `develop` into `main`.

## Known limits and gotchas

- **Memory:** evals beside the live Docker stack run the 16 GB machine out of memory. Stop the stack before an eval, and do not commit while an eval writes tracked files.
- **Groq free tier:** 8,000 tokens/min, roughly 2 verdicts per minute. The client waits out `retry-after` up to 30 s, then falls back to the local model, whose verdicts are never fast-tracked.
- **Local translations are weak:** the local model garbled disaster words in 5 of 5 sentences, so the desk marks every local translation "read every word".
- **Verdicts vary between runs** even at temperature 0. The router thresholds absorb this, so tune them on eval data.
- **The vision model does not fully fit in 8 GB VRAM** (about 29% spills to the CPU). Do not raise `num_ctx` past 8192.
- **Links:** pasted links are fetched with the browser login named in `FETCH_BROWSER` (ADR 0010). YouTube fails *with* browser cookies, so it is fetched without them. Private or deleted posts go to a checker, and the sender is asked for the file, which joins the same report.
- **The Telegram reply to a repeat** comes on the bot's next poll, up to about 25 s later.
- **Never commit while a background job writes a tracked file:** pre-commit rolls the file back to its stash and the job's writes are lost (this happened to `manifest.csv`).
- **Pre-commit leaves untracked files on disk,** so pyright can check a tree that will not exist. Commit in dependency order, never hide commit output, and check each commit landed (see `CLAUDE.md`).
- **Shell:** zsh does not word-split `$var`, and `pkill -f <pattern>` can kill its own shell. Stop services by PID.
- `graphify-out/` (a code knowledge graph) is generated and gitignored.
