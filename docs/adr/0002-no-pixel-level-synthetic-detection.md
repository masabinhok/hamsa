# 0002. No pixel-level AI-image detection; use provenance and evidence

- Status: Accepted
- Date: 2026-10-06

## Context
A large share of the August 2026 flood fakes were AI-generated video and images (AFP, BOOM, and CyberPeace each debunked several). The obvious feature is an "is this AI?" classifier. But such detectors are unreliable in the wild: they fail on new generators, on recompressed social-media video, and on real footage that has been heavily processed. A false "AI-generated" label on real disaster footage would discredit a real victim's report, which is worse than missing a fake.

## Options considered
- **Pixel-level detector** (open classifier models). Quick to bolt on, but unexplainable scores and poor robustness to recompression.
- **Provenance and evidence signals.** Visible AI-tool watermarks (Veo, Sora, Gemini), uploader handles, absence of any corroborating report, contradictions with trusted reporting.

## Decision
Do not ship a pixel-level detector. Extraction reports visible watermarks and handles as facts; the router treats an AI-tool watermark as a strong signal and lack of corroboration as a reason for human review. Synthetic posts are still in the eval set so we measure exactly how far this approach gets.

## Consequences
- Synthetic media without a visible mark and with plausible framing will reach a human as "ambiguous" or "new claim", not as "fake". That is the honest outcome.
- Every signal shown to a checker is something they can verify themselves.
- Stated as a limitation in the README.
