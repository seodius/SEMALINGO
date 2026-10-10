"""Print one summary line per word-list source: words per category and how many matched Concepticon.

Used by the Load sources workflow; run inside the image with the database in data/.
"""

import sys

import duckdb

SOURCES = sys.argv[1:]
conn = duckdb.connect("data/semalingo.duckdb", read_only=True)
for source in SOURCES:
    forms = conn.execute("SELECT COUNT(*) FROM forms WHERE source_id = ?", [source]).fetchone()[0]
    matched = conn.execute(
        "SELECT COUNT(DISTINCT from_id) FROM mappings WHERE method = 'gloss' AND from_id LIKE ?", [source + ":%"]
    ).fetchone()[0]
    rows = conn.execute(
        "SELECT value_text, COUNT(*) FROM properties WHERE source_id = ? AND property = 'category' "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 12",
        [source],
    ).fetchall()
    concepts = conn.execute("SELECT COUNT(*) FROM concepts WHERE source_id = ?", [source]).fetchone()[0]
    parts = ", ".join(f"{c}={n}" for c, n in rows)
    print(f"{source}: {forms} words, {concepts} concepts, {matched} matched to Concepticon; {parts}")
