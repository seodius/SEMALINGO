"""Print how many Open English WordNet synsets reach a SUMO term through CILI, with examples.

Used by the Load sources workflow; run inside the image with the database in data/.
"""

import duckdb

conn = duckdb.connect("data/semalingo.duckdb", read_only=True)
PATH = """
    FROM mappings o
    JOIN mappings c ON c.from_id = o.to_id AND c.from_id LIKE 'cili:%'
    JOIN mappings s ON s.to_id = c.to_id AND s.from_id LIKE 'sumo:%'
    WHERE o.from_id LIKE 'oewn:%' AND o.method = 'imported'
"""
synsets = conn.execute("SELECT COUNT(*) FROM concepts WHERE source_id = 'oewn'").fetchone()[0]
linked = conn.execute(f"SELECT COUNT(DISTINCT o.from_id) {PATH}").fetchone()[0]
print(f"oewn -> cili -> sumo: {linked} of {synsets} synsets reach a SUMO term")
rows = conn.execute(f"""
    SELECT k.gloss, s.from_id, s.mapping_type {PATH.replace('WHERE', 'JOIN concepts k ON k.concept_id = o.from_id WHERE')}
    AND k.gloss IN ('eye', 'see', 'watch', 'look', 'nut', 'peanut', 'hear', 'light')
    ORDER BY 1, 2
""").fetchall()
print("examples: " + "; ".join(f"{g} -> {t} ({m})" for g, t, m in rows[:24]))
