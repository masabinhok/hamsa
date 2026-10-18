"""How often the fact-check search finds the fact-check behind each eval label.

`uv run python -m app.eval.review_recall` from backend/ (needs FACT_CHECK_API_KEY).
Queries use the claim the pipeline extracted in the last scored run, so this measures
what a live case would search for.
"""

import json
import sys
from urllib.parse import urlsplit

from app.config import get_settings
from app.eval.dataset import load_items
from app.eval.score import EVAL_DIR, RUNS_DIR
from app.pipeline.claim_reviews import ClaimReviewSearch
from app.pipeline.contracts import Claim


def _key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.netloc.removeprefix('www.')}{parts.path.rstrip('/')}"


def main() -> int:
    settings = get_settings()
    if settings.fact_check_api_key is None:
        print("set FACT_CHECK_API_KEY in .env", file=sys.stderr)
        return 1
    search = ClaimReviewSearch(settings.fact_check_api_key.get_secret_value())

    exact = same_publisher = anything = total = 0
    for item in load_items(EVAL_DIR / "items.csv"):
        if item.fact_check_url is None:
            continue
        cached = RUNS_DIR / "default" / f"{item.id}.json"
        claim_data = (
            json.loads(cached.read_text())["outputs"]["claim"] if cached.is_file() else None
        )
        if claim_data is None:
            print(f"{item.id}: no extracted claim in the last run, skipped")
            continue
        total += 1
        wanted = _key(str(item.fact_check_url))
        found = search(Claim.model_validate(claim_data))
        keys = [_key(str(p.url)) for p in found]
        hit = wanted in keys
        publisher = any(k.split("/")[0] == wanted.split("/")[0] for k in keys)
        exact += hit
        same_publisher += publisher
        anything += bool(found)
        mark = "found" if hit else "same publisher" if publisher else f"{len(found)} other"
        print(f"{item.id}: {mark}  ({wanted.split('/')[0]})")

    print(
        f"\n{total} items with a fact-check: exact {exact}, same publisher {same_publisher}, "
        f"any result {anything}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
