"""Command line: `semalingo validate | sources | licences | init-db | fetch | add-file | load | build | stats`."""

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


def cmd_add_file(args) -> int:
    from .loaders import LOADERS, ManualLoader

    sources = {s.id: s for s in load_registry(args.registry)}
    cls = LOADERS.get(args.source)
    if cls is None or not issubclass(cls, ManualLoader):
        manual = sorted(i for i, c in LOADERS.items() if issubclass(c, ManualLoader))
        raise ValueError(f"{args.source} is not a manual source (manual sources: {', '.join(manual)})")
    target = cls(sources[args.source]).add_file(args.raw, args.path, args.name)
    print(f"Added {target}")
    return 0


def cmd_load(args, fetch_first: bool = False) -> int:
    from .db import init_db
    from .loaders import ManualSourceMissing

    loaders = selected_loaders(args)
    conn = init_db(args.db)
    try:
        for loader in loaders:
            if fetch_first:
                try:
                    timed(f"fetch {loader.source_id} {loader.ref}", lambda: loader.fetch(args.raw))
                except ManualSourceMissing as missing:
                    if args.sources:  # asked for by name: report it as an error
                        raise
                    print(f"skip {loader.source_id}: {missing}", flush=True)
                    continue
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


def cmd_match(args) -> int:
    from .db import init_db
    from .matching import INDEX_SOURCE, build_index, match_source

    conn = init_db(args.db)
    try:
        index = build_index(conn)
        if not index:
            raise RuntimeError(f"no gloss lookup loaded; run: semalingo build {INDEX_SOURCE}")
        for source_id in args.sources:
            result = timed(f"match {source_id}", lambda: match_source(conn, source_id, index, args.min_share, args.top))
            print(
                f"  {source_id}: {result['matched']} of {result['forms']} forms matched, "
                f"{result['mappings']} gloss mappings to Concepticon",
                flush=True,
            )
    finally:
        conn.close()
    return 0


def cmd_link_wordnet(args) -> int:
    from .db import init_db
    from .linking import link

    conn = init_db(args.db)
    try:
        result = timed("link concepticon -> oewn", lambda: link(conn, args.top))
        print(f"  {result['linked']} of {result['concepts']} concept sets got WordNet proposals ({result['mappings']} mappings)")
    finally:
        conn.close()
    return 0


def cmd_review_queue(args) -> int:
    import json

    from .db import init_db
    from .lists import list_ids
    from .review import DEFAULT_LISTS, WORDS, review_payload, unmatched_words

    lists = list(args.lists or DEFAULT_LISTS) + list_ids(args.custom_lists)
    conn = init_db(args.db)
    try:
        payload = review_payload(conn, lists)
        for list_id in lists:
            if list_id.endswith(WORDS):
                words = unmatched_words(conn, list_id[: -len(WORDS)])
                print(f"{list_id}: {len(words)} words match no concept set" + (f" ({', '.join(words[:40])})" if words else ""))
    finally:
        conn.close()
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(payload['items'])} concept sets ({len(payload['languages'])} languages) to {args.out}")
    return 0


def cmd_load_mappings(args) -> int:
    from .db import init_db
    from .review import load_reviewed

    found = sorted(Path("mappings").glob("*__*.tsv")) + sorted(Path("data/lists").glob("*__*.tsv"))
    paths = args.paths or [p for p in found if not p.name.endswith(".unmatched.tsv")]
    conn = init_db(args.db)
    try:
        n = load_reviewed(conn, paths)
    finally:
        conn.close()
    print(f"Loaded {n} reviewed mappings from {len(paths)} file(s)")
    return 0


def cmd_export_review(args) -> int:
    import json

    from .review import decisions_to_rows, write_review_file, write_unmatched_file

    decisions = []
    for path in sorted(Path(args.folder).rglob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        body = body.get("data", body) if isinstance(body, dict) else body
        if isinstance(body, dict) and body.get("concept") and body.get("type"):
            decisions.append(body)
    edges, unmatched = decisions_to_rows(decisions, args.reviewer)
    # decisions on new concepts from custom lists stay with those lists, outside the repository
    private = Path(args.custom_lists) / "custom__oewn.tsv"
    for out, keep in ((Path(args.out), lambda r: not r["from_id"].startswith("custom:")), (private, lambda r: r["from_id"].startswith("custom:"))):
        mine, none = [r for r in edges if keep(r)], [r for r in unmatched if keep(r)]
        if out == private and not mine and not none:
            continue
        n = write_review_file(out, mine)
        m = write_unmatched_file(out.with_name(out.name.replace(".tsv", ".unmatched.tsv")), none)
        print(f"{out}: {n} mappings, {m} concepts without an equivalent")
    print(f"{len(decisions)} decisions")
    return 0


def cmd_export_lists(args) -> int:
    from .lists import lists_from_page, write_lists

    lists = lists_from_page(Path(args.folder), args.reviewer)
    n = write_lists(Path(args.out), lists)
    print(f"Wrote {len(lists)} lists with {n} entries to {args.out}")
    return 0


def cmd_load_lists(args) -> int:
    from .db import init_db
    from .lists import load_lists

    conn = init_db(args.db)
    try:
        counts = load_lists(conn, args.folder)
    finally:
        conn.close()
    print(f"Loaded custom lists from {args.folder}: {counts['concepts']} lists and new concepts, {counts['relations']} entries")
    return 0


def cmd_check_mappings(args) -> int:
    from .db import init_db
    from .review import check, read_unmatched

    unmatched = read_unmatched(sorted(Path("mappings").glob("*.unmatched.tsv")))
    conn = init_db(args.db)
    try:
        for line in check(conn, unmatched=unmatched):
            print(line)
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

    p = sub.add_parser("add-file", help="add a manually downloaded file for a source that cannot be fetched")
    p.add_argument("source")
    p.add_argument("path", type=Path)
    p.add_argument("--as", dest="name", help="file name the loader expects, if the source expects several")
    p.add_argument("--raw", type=Path, default=DEFAULT_RAW, help="raw data folder (default: data/raw)")
    p.set_defaults(func=cmd_add_file)

    p = sub.add_parser("load", help="load fetched sources into the DuckDB core tables")
    with_sources(p)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_load)

    p = sub.add_parser("build", help="fetch (if needed) and load sources")
    with_sources(p)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=lambda a: cmd_load(a, fetch_first=True))

    p = sub.add_parser("match", help="link the words of loaded sources to Concepticon concept sets by gloss")
    p.add_argument("sources", nargs="+", help="source ids whose forms to match, e.g. subtlex-nl oewn")
    p.add_argument("--min-share", type=float, default=0.05, help="drop concept sets with a smaller share of the gloss's uses")
    p.add_argument("--top", type=int, default=5, help="keep at most this many concept sets per word")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_match)

    p = sub.add_parser("link-wordnet", help="propose WordNet synsets for every Concepticon concept set (step 4, pass 1)")
    p.add_argument("--top", type=int, default=3, help="proposals per concept set")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_link_wordnet)

    p = sub.add_parser("review-queue", help="write the proposals for a priority set of concept sets, with their words in other languages, as JSON for review")
    p.add_argument("out", type=Path)
    p.add_argument("--lists", nargs="*", help="lists that define the batch: Concepticon list ids, widely-used:<n>, <word-list source>:words (default: NSM, Swadesh, Leipzig-Jakarta, Ogden, Luniewska, widely-used:50, basic-english:words)")
    p.add_argument("--custom-lists", type=Path, default=Path("data/lists"), help="folder of custom lists to add to the batch (default: data/lists)")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_review_queue)

    p = sub.add_parser("load-mappings", help="load reviewed mappings from mappings/*__*.tsv")
    p.add_argument("paths", nargs="*", type=Path)
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_load_mappings)

    p = sub.add_parser("export-review", help="turn review-page decisions (JSON files) into mappings/concepticon__oewn.tsv")
    p.add_argument("folder", help="folder with one JSON file per decision")
    p.add_argument("--reviewer", required=True, help="name recorded for the page owner's decisions")
    p.add_argument("--out", default="mappings/concepticon__oewn.tsv")
    p.add_argument("--custom-lists", default="data/lists", help="where decisions on new concepts from custom lists go")
    p.set_defaults(func=cmd_export_review)

    p = sub.add_parser("export-lists", help="turn the review page's custom lists (JSON export) into data/lists/*.tsv")
    p.add_argument("folder", help="folder with the exported lists/<id>.json and lists/<id>/entries/*.json")
    p.add_argument("--reviewer", required=True, help="name recorded for the page owner's lists and entries")
    p.add_argument("--out", default="data/lists")
    p.set_defaults(func=cmd_export_lists)

    p = sub.add_parser("load-lists", help="load custom concept lists (data/lists) into the core tables")
    p.add_argument("--folder", type=Path, default=Path("data/lists"))
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_load_lists)

    p = sub.add_parser("check-mappings", help="quality checks on the mapping layer")
    p.add_argument("--db", type=Path, default=DEFAULT_DB)
    p.set_defaults(func=cmd_check_mappings)

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
