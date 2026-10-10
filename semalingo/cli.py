"""Command line: `semalingo validate | sources | licences | init-db`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .registry import WAVES, default_registry_path, licence_table, load_registry, read_raw, validate


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
    for s in load_registry(args.registry):
        if args.wave and s.wave != args.wave:
            continue
        if s.checked:
            status = "verified"
        elif s.open_fields:
            status = f"to verify: {', '.join(s.open_fields)}"
        else:
            status = "fields filled, not confirmed (see notes)"
        print(f"{s.wave:<7} {s.id:<24} {s.unit:<12} {status}")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="semalingo", description=__doc__)
    parser.add_argument("--version", action="version", version=f"semalingo {__version__}")
    parser.add_argument("--registry", type=Path, default=default_registry_path(), help="path to sources.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate", help="check sources.yaml").set_defaults(func=cmd_validate)

    p = sub.add_parser("sources", help="list sources and what is still unverified")
    p.add_argument("--wave", choices=WAVES)
    p.set_defaults(func=cmd_sources)

    p = sub.add_parser("licences", help="print DATA-LICENSES.md, or --write it")
    p.add_argument("--write", action="store_true")
    p.set_defaults(func=cmd_licences)

    p = sub.add_parser("init-db", help="create the core tables in a DuckDB file")
    p.add_argument("path", type=Path)
    p.set_defaults(func=cmd_init_db)
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
