"""Gloss matching: link the words of any source to Concepticon concept sets.

The index is Concepticon's own gloss lookup (source "concepticon-maps"): for each language,
which concept sets a written gloss is linked to, and how often concept lists use that link.
A word matches when its normalised spelling equals a normalised gloss in the same language.

Every match becomes a mapping edge with method "gloss" and type "close" (a likely link, not
reviewed). Its confidence is the share of the gloss's list uses that go to that concept set,
so "watch" splits between WATCH (to look at) and WRISTWATCH instead of picking one. Running a
match again replaces the gloss mappings of that source.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .languages import ENGLISH
from .writer import COLUMNS, bulk_insert, dedupe, is_duckdb

INDEX_SOURCE = "concepticon-maps"
# Leading words that glosses add but word lists do not: "the eye", "to see".
LEADING_WORDS = {ENGLISH: ("the ", "a ", "an ", "to ")}
EDGE_CHARACTERS = "*$—+ \t\"'.?!"
BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
ALTERNATIVES = re.compile(r"[,;/]")


def gloss_keys(text, language: str, split: bool = True) -> list[str]:
    """Normalised lookup keys for a gloss: lower case, no brackets, no leading article or "to".

    With split=True, "anxiety, worry" gives two keys; a word from a word list is not split.
    """
    text = BRACKETS.sub(" ", str(text or ""))
    keys: list[str] = []
    for part in ALTERNATIVES.split(text) if split else [text]:
        key = " ".join(part.casefold().split()).strip(EDGE_CHARACTERS)
        for word in LEADING_WORDS.get(language, ()):
            if key.startswith(word) and len(key) > len(word):
                key = key[len(word):].strip(EDGE_CHARACTERS)
                break
        if key and key not in keys:
            keys.append(key)
    return keys


def build_index(conn, index_source: str = INDEX_SOURCE) -> dict[tuple[str, str], list[tuple[str, float]]]:
    """(language, key) -> [(concept node, share)], best first."""
    rows = conn.execute(
        "SELECT f.language, f.written_form, m.to_id, m.confidence FROM forms f "
        "JOIN mappings m ON m.from_id = f.form_id AND m.method = 'imported' WHERE f.source_id = ?",
        [index_source],
    ).fetchall()
    index: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for language, key, concept, share in rows:
        index[(language, key)].append((concept, share))
    for candidates in index.values():
        candidates.sort(key=lambda c: (-c[1], c[0]))
    return dict(index)


def match_source(conn, source_id: str, index, min_share: float = 0.05, top: int = 5) -> dict[str, int]:
    """Write gloss mappings from the forms of one source; return counts."""
    forms = conn.execute("SELECT form_id, language, written_form FROM forms WHERE source_id = ?", [source_id]).fetchall()
    rows = []
    matched = 0
    for form_id, language, text in forms:
        candidates = []
        for key in gloss_keys(text, language, split=False):
            candidates = index.get((language, key), [])
            if candidates:
                break
        kept = [(concept, share) for concept, share in candidates if share >= min_share][:top]
        if kept:
            matched += 1
        for concept, share in kept:
            rows.append((form_id, concept, "close", share, "gloss", None))

    conn.execute("DELETE FROM mappings WHERE method = 'gloss' AND from_id LIKE ?", [source_id + ":%"])
    bulk_insert(conn, "mappings", COLUMNS["mappings"], dedupe("mappings", rows))
    if not is_duckdb(conn):
        conn.commit()
    return {"forms": len(forms), "matched": matched, "mappings": len(rows)}
