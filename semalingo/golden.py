"""Golden questions: questions with known answers that must still pass after every rebuild.

Each question in tests/golden/questions.yaml names an operation, its arguments and what the
answer must contain:

    - question: Do ARM and HAND share one word in many language families?
      operation: colexifications
      args: [concepticon:1673]
      expect:
        - {at: "clics[*].concept", contains: "concepticon:1277"}

`at` is a path into the result: keys separated by dots, `[*]` for every item of a list, `[0]`
for one. A check passes when the values found there contain `contains`, are all at least
`min`, or (with `nonempty: true`) are not empty.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .ops import Graph

STEP = re.compile(r"([^.\[\]]+)|\[(\*|\d+)\]")


def values_at(data, path: str) -> list:
    found = [data]
    for key, index in STEP.findall(path):
        nxt = []
        for item in found:
            if key:
                if isinstance(item, dict) and key in item:
                    nxt.append(item[key])
            elif index == "*":
                if isinstance(item, list):
                    nxt.extend(item)
            elif isinstance(item, list) and int(index) < len(item):
                nxt.append(item[int(index)])
        found = nxt
    return found


def check(result: dict, expect: dict) -> str | None:
    """None when the expectation holds, else what went wrong."""
    found = values_at(result, expect["at"])
    if "contains" in expect and expect["contains"] not in found:
        return f"{expect['at']} does not contain {expect['contains']!r} (found {found[:8]})"
    if "min" in expect and (not found or any(v is None or v < expect["min"] for v in found)):
        return f"{expect['at']} is below {expect['min']} (found {found[:8]})"
    if expect.get("nonempty") and not any(found):
        return f"{expect['at']} is empty"
    return None


def run(graph: Graph, questions: list[dict]) -> list[tuple[dict, list[str]]]:
    """Ask every question; return (question, problems) pairs."""
    out = []
    for q in questions:
        try:
            result = getattr(graph, q["operation"])(*q.get("args", []), **q.get("options", {}))
            problems = [p for p in (check(result, e) for e in q.get("expect", [])) if p]
        except Exception as exc:  # a broken operation is a failed question, not a crash
            problems = [f"{type(exc).__name__}: {exc}"]
        out.append((q, problems))
    return out


def read_questions(path: Path) -> list[dict]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
