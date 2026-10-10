"""Buffered writes into the core tables, the same way for SQLite (tests) and DuckDB.

A loader collects rows through a Writer and calls finish(). Loading a source again first
removes everything that source wrote before, so loads are repeatable.
"""

from __future__ import annotations

import csv
import os
import tempfile

from .registry import Source

COLUMNS = {
    "forms": ("form_id", "source_id", "language", "written_form"),
    "concepts": ("concept_id", "source_id", "kind", "gloss"),
    "relations": ("source_id", "from_id", "to_id", "relation_type", "weight"),
    "properties": ("node_id", "source_id", "property", "value_num", "value_text"),
    "mappings": ("from_id", "to_id", "mapping_type", "confidence", "method", "reviewer"),
}
# Positions of the primary-key columns in COLUMNS, used to drop duplicates before inserting.
KEYS = {
    "forms": (0,),
    "concepts": (0,),
    "relations": (0, 1, 2, 3),
    "properties": (0, 1, 2),
    "mappings": (0, 1, 2, 4),
}


def dedupe(table: str, rows: list[tuple]) -> list[tuple]:
    """Keep the first row for each primary key."""
    seen: set[tuple] = set()
    unique = []
    for row in rows:
        key = tuple(row[i] for i in KEYS[table])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def is_duckdb(conn) -> bool:
    # The connection class lives in DuckDB's compiled module, "_duckdb" in recent versions.
    kind = type(conn)
    return kind.__name__ == "DuckDBPyConnection" or "duckdb" in kind.__module__.lower()


def bulk_insert(conn, table: str, columns: tuple[str, ...], rows: list[tuple]) -> None:
    """Insert many rows that are already free of duplicate keys (see dedupe); CHECK violations raise."""
    if not rows:
        return
    names = ", ".join(columns)
    if not is_duckdb(conn):
        marks = ", ".join("?" for _ in columns)
        conn.executemany(f"INSERT OR IGNORE INTO {table} ({names}) VALUES ({marks})", rows)
        return
    # DuckDB inserts row by row through executemany; going through a CSV file is far faster.
    types = {row[1]: row[2] for row in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}
    handle = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
    try:
        with handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(tuple("" if v is None else v for v in row) for row in rows)
        spec = ", ".join(f"'{c}': '{types[c]}'" for c in columns)
        path = handle.name.replace("'", "''")
        conn.execute(
            f"INSERT INTO {table} ({names}) SELECT {names} FROM read_csv('{path}', "
            f"header = true, columns = {{{spec}}}, nullstr = '', quote = '\"', escape = '\"')"
        )
    finally:
        os.unlink(handle.name)


class Writer:
    def __init__(self, conn, source: Source, version: str):
        self.conn = conn
        self.source = source
        self.version = version
        self.buffers: dict[str, list[tuple]] = {table: [] for table in COLUMNS}

    # --- rows -------------------------------------------------------------
    def concept(self, concept_id: str, kind: str, gloss: str | None = None) -> None:
        self.buffers["concepts"].append((concept_id, self.source.id, kind, gloss))

    def form(self, form_id: str, language: str, written_form: str) -> None:
        if not written_form or not language:
            return  # a form without text or language carries nothing to compare
        self.buffers["forms"].append((form_id, self.source.id, language, written_form))

    def relation(self, from_id: str, to_id: str, relation_type: str, weight: float | None = None) -> None:
        self.buffers["relations"].append((self.source.id, from_id, to_id, relation_type, weight))

    def prop(self, node_id: str, name: str, value) -> None:
        if value is None or value == "" or value == []:
            return
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v) for v in value)
        if isinstance(value, bool):
            value = str(value).lower()
        if isinstance(value, (int, float)):
            self.buffers["properties"].append((node_id, self.source.id, name, float(value), None))
        else:
            self.buffers["properties"].append((node_id, self.source.id, name, None, str(value)))

    def mapping(self, from_id: str, to_id: str, mapping_type: str = "exact", confidence: float = 1.0) -> None:
        """A mapping the source itself provides (e.g. a Concepticon_ID column)."""
        self.buffers["mappings"].append((from_id, to_id, mapping_type, confidence, "imported", None))

    # --- lifecycle --------------------------------------------------------
    def clear(self) -> None:
        sid = self.source.id
        for table in ("forms", "concepts", "relations", "properties"):
            self.conn.execute(f"DELETE FROM {table} WHERE source_id = ?", [sid])
        self.conn.execute("DELETE FROM mappings WHERE method = 'imported' AND from_id LIKE ?", [sid + ":%"])
        self.conn.execute("DELETE FROM sources WHERE source_id = ?", [sid])

    def finish(self) -> dict[str, int]:
        """Replace this source's rows with the buffered ones; return row counts per table."""
        self.clear()
        self.conn.execute(
            "INSERT INTO sources (source_id, name, version, licence, loaded_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [self.source.id, self.source.name, self.version, self.source.licence],
        )
        for table, rows in self.buffers.items():
            bulk_insert(self.conn, table, COLUMNS[table], dedupe(table, rows))
        if not is_duckdb(self.conn):
            self.conn.commit()
        return source_counts(self.conn, self.source.id)


def source_counts(conn, source_id: str) -> dict[str, int]:
    """Rows a source has in each core table (imported mappings counted by their from_id)."""
    counts = {}
    for table in ("forms", "concepts", "relations", "properties"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE source_id = ?", [source_id]).fetchone()[0]
    counts["mappings"] = conn.execute(
        "SELECT COUNT(*) FROM mappings WHERE method = 'imported' AND from_id LIKE ?", [source_id + ":%"]
    ).fetchone()[0]
    return counts
