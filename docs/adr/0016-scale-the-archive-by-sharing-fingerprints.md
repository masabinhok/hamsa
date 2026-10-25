# 0016. Scale the archive by sharing fingerprints between desks, not by storing the world's media

- Status: Accepted (the direction; fingerprint sharing is not built)
- Date: 2026-10-24

## Context
Media matching only searches Hamsa's own archive: a few dozen seed clips plus what checkers have published since (ADR 0011, ADR 0014). The owner asked how that limit is overcome when Hamsa grows past one newsroom, and whether the answer is to download every video in advance or to search the web for each post.

The archive does not hold videos. For each keyframe it holds three fingerprints (`ArchiveIndex.add` in `backend/app/pipeline/media_match.py`): a 64-bit pHash, a SigLIP 2 vector and ORB keypoints. Measured on 2026-10-24, 325 keyframes take 32 MB in Qdrant, about 100 KB each and mostly ORB keypoints.

## Options considered
- **Download all disaster media in advance.** Rejected: unbounded storage, other people's videos on our disks, and it still misses what goes viral next (ADR 0011).
- **Automatic online reverse search for every post.** Rejected by the owner on 2026-10-24: there is no free API. Google Lens has no official API, TinEye charges per search, and Bing's search APIs were retired in 2025. Searching by the post's words recovered 0 of 9 originals (ADR 0011). Checkers keep one-click Lens, Yandex and TinEye from the desk, and Hamsa remembers what they find.
- **Share fingerprints and labels between desks, and seed from free sources.** Chosen.

## Decision
The archive grows in three ways, none of which stores media it does not need:
1. **By use (built).** Every verdict a checker publishes as true, false or misleading is fingerprinted into the archive, and so is the original a checker pastes into "Original found at" (`teach` in `backend/app/learn.py`). Exact repeats (same link, platform post ID or file) merge before any model runs.
2. **Across newsrooms (the scale step, not built).** Each newsroom runs its own desk. Desks exchange fingerprints with their label, context and report link, never the media. A verdict published at one desk then catches the same footage at every other. Platforms already share known harmful media this way: the GIFCT hash-sharing database and StopNCII share hashes, not content.
3. **From free feeds (not built).** Trusted outlets' and agencies' own video channels (AFP, AP, Kantipur, NDRRMA) are fingerprinted as `verified_genuine` the way `corpus watch` follows RSS today. The original footage that fact-check articles cite is fingerprinted as debunked, but never the fact-check's own images, which carry its stamps.

## Consequences
- Storage grows with keyframes, not video: about 100 KB per keyframe, so a million keyframes is about 100 GB in Qdrant, which shards across machines.
- Recall on recycled footage grows with use and with the number of desks sharing. It is still bounded by what someone has checked, so footage nobody has seen before always reaches a human, with news, fact-checks and web evidence.
- Sharing needs trust between desks. A shared fingerprint carries the publishing desk's name, and each desk decides whose labels may fast-track its cases. The router already treats Hamsa's own published verdicts as strong evidence; a partner desk's would follow the same rule.
- Hamsa does not learn by training. It remembers published verdicts; models, prompts and thresholds change only in code, so every decision stays auditable.
