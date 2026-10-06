"""Media match (architecture 3.3, ADR 0003): pHash and SigLIP against the archive.

Each archive frame is stored in Qdrant with two named vectors:
- `siglip`: an L2-normalised SigLIP image embedding, searched by cosine.
- `phash`: the 64-bit perceptual hash as a +1/-1 vector, searched by dot product.
  For such vectors dot = 64 - 2 * hamming, so the search ranks by exact Hamming distance.
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast

import imagehash
import numpy as np
import torch
from numpy.typing import NDArray
from PIL import Image, ImageChops, ImageOps
from qdrant_client import QdrantClient, models
from transformers import AutoImageProcessor, SiglipVisionModel
from transformers.utils import logging as transformers_logging

from app.ingest.frames import Frame
from app.pipeline.contracts import ArchiveHit, ArchiveLabel, MediaMatch

PHASH_BITS = 64
SIGLIP_MODEL = "google/siglip2-base-patch16-224"
SIGLIP_DIM = 768
COLLECTION = "archive_frames"
SEARCH_LIMIT = 10
# Candidates weaker than both floors are noise, not worth a checker's attention.
CANDIDATE_MAX_PHASH = 20
CANDIDATE_MIN_COSINE = 0.75

# Border trimming: pixels within this distance of the corner colour count as border; a
# row or column is content when more than CONTENT_SHARE of it differs (so a status-bar
# clock does not stop the trim); a trim must keep MIN_KEPT_AREA or it is cutting content.
BORDER_TOLERANCE = 20
CONTENT_SHARE = 0.05
MIN_KEPT_AREA = 0.25

Embeddings = NDArray[np.float32]
Embed = Callable[[Sequence[Image.Image]], Embeddings]


def canonical(image: Image.Image) -> Image.Image:
    """Strip uniform bars and screenshot chrome, which reposts add and pHash is sensitive to.

    Applied identically to archive frames and submitted frames. Blurred-background bars
    (TikTok style) are not stripped: a gradient-based trim also ate caption banners.
    """
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    difference = np.asarray(ImageChops.difference(rgb, background).convert("L"))
    differs = difference > BORDER_TOLERANCE
    rows = np.flatnonzero(differs.mean(axis=1) > CONTENT_SHARE)
    cols = np.flatnonzero(differs.mean(axis=0) > CONTENT_SHARE)
    if rows.size == 0 or cols.size == 0:
        return rgb
    left, top, right, bottom = int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1
    kept = (right - left) * (bottom - top) / (rgb.width * rgb.height)
    return rgb.crop((left, top, right, bottom)) if kept >= MIN_KEPT_AREA else rgb


def phash_vector(image: Image.Image) -> list[float]:
    bits = cast(NDArray[np.bool_], imagehash.phash(image).hash)  # pyright: ignore[reportUnknownMemberType]
    return [1.0 if bit else -1.0 for bit in bits.flatten()]


def hamming(a: Sequence[float], b: Sequence[float]) -> int:
    dot = float(np.dot(a, b))
    return round((PHASH_BITS - dot) / 2)


class SiglipEmbedder:
    """SigLIP vision tower on CPU. Loads lazily: the weights are ~400 MB."""

    def __init__(self, model_name: str = SIGLIP_MODEL) -> None:
        self._model_name = model_name
        self._model: Any = None
        self._processor: Any = None

    def __call__(self, images: Sequence[Image.Image]) -> Embeddings:
        processor, model = self._load()
        inputs: dict[str, torch.Tensor] = processor(images=list(images), return_tensors="pt")
        with torch.inference_mode():
            pooled: torch.Tensor = model(**inputs).pooler_output
        normalised = torch.nn.functional.normalize(pooled, dim=-1)
        return normalised.numpy().astype(np.float32)

    def _load(self) -> tuple[Any, Any]:
        if self._model is None:
            # The checkpoint includes the text tower we skip; its load report is noise.
            transformers_logging.set_verbosity_error()
            # Cache first: an online revision check stalled one pipeline run for 90 s.
            try:
                self._processor, self._model = self._from_pretrained(local_files_only=True)
            except OSError:
                self._processor, self._model = self._from_pretrained(local_files_only=False)
        return self._processor, self._model

    def _from_pretrained(self, *, local_files_only: bool) -> tuple[Any, Any]:
        name = self._model_name
        processor = cast(
            Any,
            AutoImageProcessor.from_pretrained(name, local_files_only=local_files_only),  # pyright: ignore[reportUnknownMemberType]
        )
        model = SiglipVisionModel.from_pretrained(name, local_files_only=local_files_only)  # pyright: ignore[reportUnknownMemberType]
        return processor, model.eval()


@dataclass(frozen=True)
class ArchiveEntry:
    archive_id: str
    label: ArchiveLabel
    original_context: str
    original_date: date | None
    source_url: str


class ArchiveIndex:
    def __init__(self, client: QdrantClient, collection: str = COLLECTION) -> None:
        self._client = client
        self._collection = collection

    def recreate(self) -> None:
        if self._client.collection_exists(self._collection):
            self._client.delete_collection(self._collection)
        self._client.create_collection(
            self._collection,
            vectors_config={
                "siglip": models.VectorParams(size=SIGLIP_DIM, distance=models.Distance.COSINE),
                "phash": models.VectorParams(size=PHASH_BITS, distance=models.Distance.DOT),
            },
        )

    def add(self, entry: ArchiveEntry, frames: Sequence[Frame], embed: Embed) -> int:
        images = [canonical(f.image) for f in frames]
        embeddings = embed(images)
        points = [
            models.PointStruct(
                id=_point_id(entry.archive_id, frame.index),
                vector={"siglip": embedding.tolist(), "phash": phash_vector(image)},
                payload={
                    "archive_id": entry.archive_id,
                    "frame_index": frame.index,
                    "label": entry.label.value,
                    "original_context": entry.original_context,
                    "original_date": entry.original_date.isoformat()
                    if entry.original_date
                    else None,
                    "source_url": entry.source_url,
                },
            )
            for frame, image, embedding in zip(frames, images, embeddings, strict=True)
        ]
        self._client.upsert(self._collection, points=points)
        return len(points)

    def candidates(
        self, siglip: list[float], phashes: Sequence[list[float]]
    ) -> list[models.ScoredPoint]:
        """Nearest archive frames by any query vector, with stored vectors attached."""
        found: dict[str, models.ScoredPoint] = {}
        queries = [("siglip", siglip), *(("phash", phash) for phash in phashes)]
        for using, query in queries:
            response = self._client.query_points(
                self._collection,
                query=query,
                using=using,
                limit=SEARCH_LIMIT,
                with_payload=True,
                with_vectors=True,
            )
            for point in response.points:
                found.setdefault(str(point.id), point)
        return list(found.values())


def match_media(frames: Sequence[Frame], index: ArchiveIndex, embed: Embed) -> MediaMatch:
    """Best hit per archive item across all submitted frames, strongest first."""
    if not frames:
        return MediaMatch()

    best: dict[str, ArchiveHit] = {}
    images = [canonical(f.image) for f in frames]
    for frame, image, embedding in zip(frames, images, embed(images), strict=True):
        siglip = embedding.tolist()
        # Reposts are often mirrored, which flips about half the hash bits.
        phashes = [phash_vector(image), phash_vector(ImageOps.mirror(image))]
        for point in index.candidates(siglip, phashes):
            vectors: Any = point.vector
            payload: Any = point.payload
            distance = min(hamming(phash, vectors["phash"]) for phash in phashes)
            cosine = round(float(np.dot(siglip, vectors["siglip"])), 4)
            if distance > CANDIDATE_MAX_PHASH and cosine < CANDIDATE_MIN_COSINE:
                continue
            hit = ArchiveHit(
                archive_id=payload["archive_id"],
                frame_index=frame.index,
                phash_distance=distance,
                cosine=cosine,
                archive_label=ArchiveLabel(payload["label"]),
                original_context=payload["original_context"],
                original_date=payload["original_date"],
                source_url=payload["source_url"],
            )
            current = best.get(hit.archive_id)
            if current is None or _strength(hit) > _strength(current):
                best[hit.archive_id] = hit

    return MediaMatch(hits=sorted(best.values(), key=_strength, reverse=True))


def _strength(hit: ArchiveHit) -> tuple[int, float]:
    # Fewer differing hash bits first, then higher cosine. Both are always set here.
    return (-(hit.phash_distance or 0), hit.cosine or 0.0)


def _point_id(archive_id: str, frame_index: int) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"hamsa:{archive_id}:{frame_index}"))
