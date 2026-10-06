# Hamsa: working notes for Claude

Hamsa is a fact-check triage desk for Nepali disaster misinformation, built solo for Frogtoberfest 2026 (demo day Oct 30). The README covers what it does; `docs/architecture.md` holds the contracts; `docs/adr/` records why.

## Hard constraints
- Open-weight models only, end to end. No OpenAI, Anthropic, or Gemini calls anywhere, not even in scripts.
- Every model call must be load-bearing: its output drives the router or the desk. Keep the README "AI usage disclosure" table accurate (file and function) whenever a model call is added or moved.
- Target hardware: 8 GB VRAM, 16 GB RAM. The GPU is reserved for the vision LLM; embedders run on CPU.

## Engineering rules
- Prove it works: every change ships with a test, an eval run, or a command that was actually run. Say which.
- No speculative abstraction. One implementation means no interface, no plugin registry, no config knob nobody sets.
- Model outputs are parsed into Pydantic models; every call has an explicit failure path (retry, fallback model, or route to a human). No LangChain or similar frameworks.
- Comments explain why, never what. No leftover TODOs or placeholder code.
- New dependencies need a one-line justification in the commit body.
- Eval data (`data/eval/`) is ground truth, independent of pipeline schemas; a scorer maps pipeline output onto labels.

## Layout
- `backend/`: uv project, package `app` (FastAPI). Run tools from `backend/`: `uv run ruff check`, `uv run ruff format`, `uv run pyright`, `uv run pytest`.
- `frontend/`: Next.js checker desk (not started).
- `docs/architecture.md`: system, schemas, router rules, failure modes, flows (Mermaid).
- `docs/adr/NNNN-title.md`: one decision per file (context, options, decision, consequences). Only for decisions with a real rejected alternative.

## Git
- Git-flow: `main` (releases), `develop` (integration), `feature/*`, `chore/*`, `fix/*`, `docs/*`.
- Conventional commits, all lowercase, no emojis, no co-author or tool attribution lines.
- Commit freely on feature branches; once lint, types, and tests pass, merge into `develop` with `--no-ff` (no per-branch owner review).
- Never push to the remote until the owner says so.
- Pre-commit stashes unstaged changes but leaves untracked files on disk, so pyright checks a tree that will not exist. Commit in dependency order, never hide commit output, and check each commit landed. If history gets tangled, stash everything (`git stash -u`) and restore files commit by commit.
