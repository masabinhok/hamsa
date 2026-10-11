"""Claim extraction with Qwen3-VL (architecture 3.2).

`uv run python -m app.pipeline.extract <media> [--text "post text"]` prints the Claim
for a local image or video, for trying the stage by hand.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.ingest.frames import Frame, frames_of
from app.llm.ollama import OllamaClient
from app.pipeline.contracts import Claim

SYSTEM = """\
You extract the factual claim from a social media post about a disaster in Nepal, for \
fact-checkers. You do not judge whether it is true. Report only what the post states or \
what is visibly present in the frames; never infer or add knowledge.

Fields:
- claim: the central factual assertion, in the post's original language and script. \
If the post is Nepali, write Nepali in Devanagari. If there is no post text, or only \
an exclamation, prayer, or emoji, describe what the media is presented as showing, in \
English (e.g. "This video shows a flood sweeping through a market in Nepal").
- claim_en: the same claim in English. Keep Nepali calendar (Bikram Sambat) dates as \
they are, e.g. "Bhadra 12 (Nepali calendar)": भदौ is not August and २०८३ is not a \
Gregorian year.
- places: every place named anywhere: in the post text (the place the claim is \
about, e.g. "रसुवा") and in on-screen text (e.g. "Columbia Glacier"). Full names in \
the original script; "मेलम्ची बजार" is one place, not two.
- claimed_date: only if the post states a Gregorian date (YYYY-MM-DD); null for \
Nepali calendar dates and when no date is stated.
- numbers: every number the claim depends on (deaths, missing, rainfall, money); \
unit and refers_to in English, e.g. value 50, unit "people", refers_to "missing".
- visible_text: on-screen text in the frames (captions, banners, signs), verbatim.
- watermarks: logos, channel marks, and generator marks visible in the frames, such as \
a TV channel logo or "Veo", "Sora", or "Gemini". Empty if none.
- handles: usernames or page names visible in the text or frames, such as @name.
- checkable: false only if the post makes no factual assertion (prayers, opinions, \
condolences) and shows no disaster footage. Disaster footage shared with only an \
exclamation or prayer is checkable: it is presented as a real event.
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

    frames = frames_of(args.media) if args.media else []

    settings = get_settings()
    client = OllamaClient(str(settings.ollama_host))
    claim = extract_claim(client, settings.vision_model, args.text, frames)
    print(claim.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
