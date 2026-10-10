"""Command line: `semalingo validate | sources | licences | init-db | fetch | load | build | stats`."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .registry import WAVES, default_registry_path, licence_table, load_registry, read_raw, validate

DEFAULT_RAW = Path("data/raw")
DEFAULT_DB = Path("data/semalingo.duckdb")


def licences_path(registry: Path) -> Path:
    return registry.resolve().parent / "DATA-LICENSES.md"


def cmd_validate(args) -> int:
    problems = validate(read_raw(args.registry))
    if problems:
        print("Source registry has problems:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    sources = load_registry(args.registry)
    counts = ", ".join(f"{sum(s.wave == w for s in sources)} {w}" for w in WAVES)
    checked = sum(s.checked for s in sources)
    print(f"Registry OK: {len(sources)} sources ({counts}); {checked} verified.")
    return 0


def cmd_sources(args) -> int:
    from .loaders import LOADERS

    for s in load_registry(args.registry):
        if args.wave and s.wave != args.wave:
            continue
        if s.checked:
            status = "verified"
        elif s.open_fields:
            status = f"to verify: {', '.join(s.open_fields)}"
        else:
            status = "fields filled, not confirmed (see notes)"
        loader = "loader" if s.id in LOADERS else "      "
        print(f"{s.wave:<7} {s.id:<24} {s.unit:<12} {loader}  {status}")
    return 0


def cmd_licences(args) -> int:
    text = licence_table(load_registry(args.registry)) + "\n"
    if args.write:
        target = licences_path(args.registry)
        target.write_text(text, encoding="utf-8")
        print(f"Wrote {target}")
    else:
        print(text, end="")
    return 0


def cmd_init_db(args) -> int:
    from .db import init_db

    conn = init_db(args.path)
    conn.close()
    print(f"Core tables ready in {args.path}")
    return 0


def selected_loaders(args):
    """Loader instances for the requested source ids (default: every source that has a loader)."""
    from .loaders import LOADERS

    sources = {s.id: s for s in load_registry(args.registry)}
    ids = args.sources or sorted(LOADERS)
    unknown = [i for i in ids if i not in LOADERS]
    if unknown:
        raise ValueError(f"no loader for: {', '.join(unknown)} (available: {', '.join(sorted(LOADERS))})")
    return [LOADERS[i](sources[i]) for i in ids]


def timed(label: str, action):
    print(f"{label} ...", flush=True)
    start = time.monotonic()
    result = action()
    print(f"{label} done in {time.monotonic() - start:.1f}s", flush=True)
    return result


def cmd_fetch(args) -> int:
    for loader in selected_loaders(args):
        folder = timed(f"fetch {loader.source_id} {loader.ref}", lambda: loader.fetch(args.raw, force=args.force))
        print(f"  -> {folder}")
    return 0


def print_counts(source_id: str, counts: dict[str, int]) -> None:
    summary = ", ".join(f"{n} {table}" for table, n in counts.items() if n)
    print(f"  {source_id}: {summary or 'nothing loaded'}", flush=True)


def cmd_load(args, fetch_first: bool = False) -> int:
    from .db import init_db

    loaders = selected_loaders(args)
    conn = init_db(args.db)
    try:
        for loader in loaders:
            if fetch_first:
                timed(f"fetch {loader.source_id} {loader.ref}", lambda: loader.fetch(args.raw))
            counts = timed(f"load {loader.source_id}", lambda: loader.load(conn, args.raw))
            print_counts(loader.source_id, counts)
    finally:
        conn.close()
    return 0


def cmd_stats(args) -> int:
    from .db import init_db
    from .writer import source_counts

    conn = init_db(args.db)
    try:
        rows = conn.execute("SELECT source_id, version, loaded_at FROM sources ORDER BY source_id").fetchall()
        if not rows:
            print("No sources loaded yet.")
        for source_id, version, loaded_at in rows:
            print(f"{source_id} {version} (loaded {loaded_at})")
            print_counts(source_id, source_counts(conn, source_id))
    finally:
        conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="semalingo", description=__doc__)
    parser.add_argument("--version", action="version", version=f"semalingo {__version__}")
    parser.add_argument("--registry", type=Path, default=default_registry_path(), help="path to sources.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="check sources.yaml").set_defaults(func=cmd_validate)

    p = sub.add_parser("sources", help="list sources, whether they have a loader, and what is still unverified")
    p.add_argument("--wave", choices=WAVES)
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("licences", help="print DATA-LICENSES.md, or --write it")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_licences)

    p = sub.add_parser("init-db", help="create the core tables in a DuckDB file")
    p.add_argument("path", type=Path)
    p.set_defaults(func=cmd_init_db)

    def with_sources(p):
        p.add_argument("sources", nargs="*", help="source ids (default: all sources with a loader)")
        p.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="raw data folder (default: data/raw)")

    p = sub.add_parser("fetch", help="download sources into the pinned raw layer")
    with_sources(p)
    p.add_argument("--force", action="store_true", help="download again even if an intact copy exists")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("load", help="load fetched sources into the DuckDB core tables")
    with_sources(p)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("build", help="fetch (if needed) and load sources")
    with_sources(p)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=lambda a: cmd_load(a, fetch_first=True))

    p = sub.add_parser("stats", help="row counts per loaded source")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError) as exc:
        print(f"semalingo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
