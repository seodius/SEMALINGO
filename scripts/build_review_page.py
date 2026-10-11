"""Build the review page for a batch of Concepticon -> WordNet proposals.

    semalingo review-queue queue.json
    python scripts/build_review_page.py queue.json review.html

The page is published as a claude.ai artifact with the db and user capabilities; each decision
is stored there and exported to mappings/concepticon__oewn.tsv (see semalingo.review).
"""

import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).with_name("review_page.html")


def main(queue_path: str, out_path: str) -> None:
    payload = json.loads(Path(queue_path).read_text(encoding="utf-8"))
    if isinstance(payload, list):  # a queue without words in other languages
        payload = {"languages": {}, "items": payload}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*QUEUE*/", data)
    Path(out_path).write_text(page, encoding="utf-8")
    print(f"Wrote {out_path}: {len(payload['items'])} concept sets, {len(page) // 1024} KB")


if __name__ == "__main__":
    main(*sys.argv[1:3])
