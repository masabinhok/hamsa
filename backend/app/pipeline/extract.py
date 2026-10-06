"""Claim extraction with Qwen3-VL (architecture 3.2).

`uv run python -m app.pipeline.extract <media> [--text "post text"]` prints the Claim
for a local image or video, for trying the stage by hand.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.ingest.frames import Frame, frames_from_image, keyframes_from_video
from app.llm.ollama import OllamaClient
from app.pipeline.contracts import Claim

SYSTEM = """\
You extract the factual claim from a social media post about a disaster in Nepal, for \
fact-checkers. You do not judge whether it is true. Report only what the post states or \
what is visibly present in the frames; never infer or add knowledge.

Fields:
- claim: the central factual assertion, in the post's original language and script. \
If the post is Nepali, write Nepali in Devanagari. If there is no post text, describe \
what the media is presented as showing, in English.
- claim_en: the same claim in English.
- places: every place named anywhere: in the post text (the place the claim is \
about, e.g. "रसुवा") and in on-screen text (e.g. "Columbia Glacier"). Full names in \
the original script; "मेलम्ची बजार" is one place, not two.
- claimed_date: only if the post states a date (YYYY-MM-DD); otherwise null.
- numbers: every number the claim depends on (deaths, missing, rainfall, money); \
unit and refers_to in English, e.g. value 50, unit "people", refers_to "missing".
- visible_text: on-screen text in the frames (captions, banners, signs), verbatim.
- watermarks: logos, channel marks, and generator marks visible in the frames, such as \
a TV channel logo or "Veo", "Sora", or "Gemini". Empty if none.
- handles: usernames or page names visible in the text or frames, such as @name.
- checkable: false only if the post makes no factual assertion (prayers, opinions, \
condolences); true otherwise.
"""


def build_prompt(text: str | None, frame_count: int) -> str:
    post = text.strip() if text and text.strip() else "(no text, media only)"
    media = f"{frame_count} frame(s) from the post's media are attached." if frame_count else ""
    return f"Post text:\n{post}\n\n{media}".strip()


def extract_claim(
    client: OllamaClient, model: str, text: str | None, frames: Sequence[Frame]
) -> Claim:
    return client.structured(
        model,
        Claim,
        system=SYSTEM,
        prompt=build_prompt(text, len(frames)),
        images=[f.image for f in frames],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract the claim from a post.")
    parser.add_argument("media", type=Path, nargs="?")
    parser.add_argument("--text")
    args = parser.parse_args()

    frames: list[Frame] = []
    if args.media:
        is_image = args.media.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
        frames = frames_from_image(args.media) if is_image else keyframes_from_video(args.media)

    settings = get_settings()
    client = OllamaClient(str(settings.ollama_host))
    claim = extract_claim(client, settings.vision_model, args.text, frames)
    print(claim.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
