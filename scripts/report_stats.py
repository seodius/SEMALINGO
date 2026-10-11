"""Print row counts for every loaded source, three sources per line (CI annotations are capped at ten per step)."""

import duckdb

conn = duckdb.connect("data/semalingo.duckdb", read_only=True)
TABLES = ("languages", "forms", "concepts", "relations", "properties")
parts = []
for source_id, version in conn.execute("SELECT source_id, version FROM sources ORDER BY source_id").fetchall():
    counts = [f"{conn.execute(f'SELECT COUNT(*) FROM {t} WHERE source_id = ?', [source_id]).fetchone()[0]} {t}" for t in TABLES]
    mappings = conn.execute("SELECT COUNT(*) FROM mappings WHERE method = 'imported' AND from_id LIKE ?", [source_id + ":%"]).fetchone()[0]
    counts.append(f"{mappings} mappings")
    parts.append(f"{source_id} {version}: " + ", ".join(c for c in counts if not c.startswith("0 ")))
for i in range(0, len(parts), 3):
    print(" | ".join(parts[i:i + 3]))
