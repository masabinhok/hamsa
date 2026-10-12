"""Run a post through the whole pipeline, from backend/:

    uv run python -m app.pipeline [media ...] --text "post text"

Needs Qdrant (docker compose up -d), Ollama, the archive, and the evidence corpus.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from qdrant_client import QdrantClient

from app.config import Settings, get_settings
from app.ingest.frames import Frame
from app.llm.groq import GroqClient
from app.llm.ollama import OllamaClient
from app.pipeline.contracts import Claim
from app.pipeline.extract import extract_claim
from app.pipeline.media_match import ArchiveIndex, SiglipEmbedder
from app.pipeline.retrieve import EvidenceStore
from app.pipeline.run import Pipeline, Result, run
from app.pipeline.verdict import Reasoner


def build_pipeline(settings: Settings) -> Pipeline:
    ollama = OllamaClient(str(settings.ollama_host))
    qdrant = QdrantClient(url=str(settings.qdrant_url))
    reasoners: list[tuple[Reasoner, str]] = []
    checker: tuple[Reasoner, str] | None = None
    if settings.groq_api_key is not None:
        groq = GroqClient(settings.groq_api_key.get_secret_value())
        reasoners.append((groq, settings.reasoning_model))
        checker = (groq, settings.checking_model)
    reasoners.append((ollama, settings.vision_model))  # fallback (ADR 0001, 0007)

    def extract(text: str | None, frames: Sequence[Frame]) -> Claim:
        return extract_claim(ollama, settings.vision_model, text, frames)

    def embed_text(texts: Sequence[str]) -> list[list[float]]:
        return ollama.embed(settings.embedding_model, texts)

    return Pipeline(
        extract=extract,
        archive=ArchiveIndex(qdrant),
        embed_image=SiglipEmbedder(),
        evidence=EvidenceStore(qdrant),
        embed_text=embed_text,
        reasoners=reasoners,
        incident_start=settings.incident_start,
        nepali_checker=checker,
    )


def report(result: Result) -> str:
    out = result.outputs
    decision = result.decision
    lines = [f"ROUTE: {decision.route}", *(f"  - {reason}" for reason in decision.reasons)]
    if out.claim:
        lines += ["", f"CLAIM: {out.claim.claim}", f"       {out.claim.claim_en}"]
    if out.media_match and out.media_match.hits:
        lines += ["", "ARCHIVE:"]
        lines += [
            f"  {h.archive_label}: {h.original_context} (phash {h.phash_distance}, cos {h.cosine})"
            for h in out.media_match.hits[:3]
        ]
    if out.verdict:
        v = out.verdict
        fallback = " [fallback]" if v.fallback else ""
        lines += ["", f"VERDICT: {v.label} ({v.confidence:.2f}) by {v.model}{fallback}"]
        lines += [f"  {v.rationale_en}", f"  {v.rationale_ne}"]
        if out.evidence:
            for citation in v.citations:
                passage = out.evidence.by_id(citation.passage_id)
                if passage:
                    lines.append(f"  {citation.stance}: {passage.source} {passage.url}")
    lines += ["", "SECONDS: " + ", ".join(f"{k} {v}" for k, v in result.seconds.items())]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a post through the pipeline.")
    parser.add_argument("media", type=Path, nargs="*")
    parser.add_argument("--text")
    args = parser.parse_args()
    result = run(build_pipeline(get_settings()), args.text, args.media)
    print(report(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
