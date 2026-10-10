"""Create the core tables in a DuckDB file."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

CORE_TABLES = ("sources", "languages", "forms", "concepts", "relations", "properties", "mappings")


def schema_sql() -> str:
    return resources.files("semalingo").joinpath("schema/core.sql").read_text(encoding="utf-8")


def statements(sql: str) -> list[str]:
    """Split the schema into statements, dropping `--` comments (the schema has no ';' inside strings)."""
    lines = [line.split("--", 1)[0] for line in sql.splitlines()]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def apply_schema(conn) -> None:
    """Create the core tables on any DB-API style connection (DuckDB or SQLite)."""
    for stmt in statements(schema_sql()):
        conn.execute(stmt)


def init_db(path: str | Path):
    """Open (or create) a DuckDB database at `path`, create the core tables, return the connection."""
    try:
        import duckdb
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError("DuckDB is not installed: pip install duckdb") from exc
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    apply_schema(conn)
    return conn
