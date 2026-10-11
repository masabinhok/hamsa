# 0008. Qdrant as the vector store

- Status: Accepted
- Date: 2026-10-06

## Context
Three similarity searches are needed: SigLIP vectors for the media archive, bge-m3 vectors for the evidence corpus, and bge-m3 vectors for open claims (duplicate detection). Each needs payload filters (archive label, source kind, publication date).

## Options considered
- **FAISS.** Fast, but an index library, not a store: filtering and persistence would be ours to build.
- **Chroma.** Easy embedded mode, but filtering and multi-vector support are weaker.
- **pgvector.** Strong, but means running Postgres, which ADR 0005 avoids.
- **Qdrant.** One container, payload filtering, persistence, and a typed Python client.

## Decision
Qdrant 1.19 in Docker, bound to localhost, with one collection per search: `archive_frames`, `evidence_passages`, `open_claims`.

## Consequences
- One container to run (`docker compose up -d`).
- Collections are rebuilt from source data by scripts, so Qdrant storage is disposable and gitignored.
