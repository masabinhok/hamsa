"""Check the eval set: `uv run python -m app.eval.validate` from backend/."""

import sys
from collections import Counter

from app.config import REPO_ROOT
from app.eval.dataset import DatasetError, load_items

EVAL_DIR = REPO_ROOT / "data" / "eval"


def main() -> int:
    try:
        items = load_items(EVAL_DIR / "items.csv", media_dir=EVAL_DIR / "media")
    except DatasetError as error:
        print(f"{len(error.problems)} problem(s) in items.csv:", file=sys.stderr)
        for problem in error.problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    print(f"{len(items)} items valid")
    if not items:
        return 0
    for field in ("verdict", "tactic", "kind", "platform"):
        counts = Counter(str(getattr(item, field)) for item in items)
        print(f"  {field}: " + ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
