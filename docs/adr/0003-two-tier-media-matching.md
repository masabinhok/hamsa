# 0003. Two-tier media matching: pHash, then SigLIP

- Status: Accepted
- Date: 2026-10-06

## Context
Recycled footage is the most common flood fake and the most provable: if a clip matches a 2023 video from Himachal Pradesh, the post is false and the checker can see both side by side. Reposts arrive re-encoded, cropped, mirrored, with captions and logos added, or as a screen recording of another phone.

## Options considered
- **Exact hashes (sha256).** Catch only byte-identical files; useless after any re-encode.
- **Perceptual hash (pHash) only.** Fast, explainable, robust to re-encoding and resizing; breaks on crops, overlays, and mirroring.
- **Image embeddings (SigLIP) only.** Robust to crops and overlays, but a high cosine can also mean "different flood, similar river", so it is weaker evidence on its own.
- **Both, in order.**

## Decision
Hash every keyframe with pHash and embed it with SigLIP. A small Hamming distance is near-certain proof; a high SigLIP cosine is a near-duplicate candidate shown with the original for the checker to confirm. Thresholds are tuned on the eval set.

## Consequences
- Matching is only as good as the archive. Building the archive (originals behind every eval item, plus verified genuine incident footage) is real work, and brand-new fakes will not match anything.
- SigLIP adds a torch dependency (CPU wheels only).
- Archive items carry a label (`prior` or `verified_genuine`), so a match can support a post as well as refute it.
