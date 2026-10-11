"""Print the Kaikki morphology summary: relation counts, most productive affixes, examples.

Used by the Load sources workflow; run inside the image with the database in data/.
"""

import duckdb

conn = duckdb.connect("data/semalingo.duckdb", read_only=True)
EXAMPLES = {
    "kaikki-en": ["readable", "unhappiness", "eyeball", "eyesight", "childlike", "reread", "rewatch", "foresee", "peanut", "eyewitness"],
    "kaikki-nl": ["leesbaar", "woordenboek", "oogappel", "kinderlijk", "herlezen", "voorzien", "pinda", "ooggetuige"],
}
for source, words in EXAMPLES.items():
    version = conn.execute("SELECT version FROM sources WHERE source_id = ?", [source]).fetchone()
    if not version:
        continue
    forms = conn.execute("SELECT COUNT(*) FROM forms WHERE source_id = ?", [source]).fetchone()[0]
    kinds = conn.execute(
        "SELECT relation_type, COUNT(*) FROM relations WHERE source_id = ? GROUP BY 1 ORDER BY 2 DESC", [source]
    ).fetchall()
    print(f"{source} {version[0]}: {forms} words; " + ", ".join(f"{k}={n}" for k, n in kinds))
    for relation in ("has_suffix", "has_prefix"):
        top = conn.execute(
            "SELECT f.written_form, COUNT(*) FROM relations r JOIN forms f ON f.form_id = r.to_id "
            "WHERE r.source_id = ? AND r.relation_type = ? GROUP BY 1 ORDER BY 2 DESC LIMIT 25",
            [source, relation],
        ).fetchall()
        print(f"{source} top {relation}: " + ", ".join(f"{w} {n}" for w, n in top))
    rows = conn.execute(
        "SELECT a.written_form, r.relation_type, b.written_form FROM relations r "
        "JOIN forms a ON a.form_id = r.from_id JOIN forms b ON b.form_id = r.to_id "
        f"WHERE r.source_id = ? AND a.written_form IN ({', '.join('?' for _ in words)}) ORDER BY 1, 2, 3",
        [source, *words],
    ).fetchall()
    print(f"{source} examples: " + "; ".join(f"{a} {t.removeprefix('has_')} {b}" for a, t, b in rows))
