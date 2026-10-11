"""Custom concept lists: your own lists of existing concept sets and of new concepts.

A list holds entries. An entry is either an existing concept (a node id such as
"concepticon:1209") or a new concept that no source has yet, with a gloss, a definition, an
ontological category and, optionally, the Concepticon concept set it is closest to and how it
relates to it ("exact", "broader", "narrower" or "related": what the closest concept set is,
seen from the new concept).

Lists live as TSV files in one folder, by default data/lists/ (outside version control, so
private lists stay private):

- index.tsv: one row per list (LIST_COLUMNS);
- <list id>.tsv: the list's entries (ENTRY_COLUMNS).

`load_lists` puts them in the core tables as source "custom": each list is a concept of kind
"list" (custom:list/<id>), each entry an "in_list" relation to it, each new concept a concept
custom:concept/<key> with its definition and category and its link to the closest concept
set. The review page keeps lists in its own store; `lists_from_page` turns an export of that
store into the TSV files.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .registry import Source
from .writer import Writer

SOURCE = Source(
    id="custom", name="Custom concept lists", wave="", unit="concept", homepage="", download="", format="tsv",
    version="local", licence="", redistributable="no",
)
DEFAULT_FOLDER = Path("data/lists")
LIST_COLUMNS = ("id", "name", "description", "created_by", "created_at")
ENTRY_COLUMNS = ("key", "concept", "gloss", "definition", "category", "closest", "relation", "note", "added_by", "added_at")
RELATIONS = ("exact", "broader", "narrower", "related")
LIST_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def list_node(list_id: str) -> str:
    return f"custom:list/{list_id}"


def concept_node(key: str) -> str:
    return f"custom:concept/{key}"


def slug(text: str) -> str:
    """A key for a list or a new concept: "Agent of (doer)" -> agent-of-doer."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").casefold()).strip("-")[:64]


def _write_tsv(path: Path, columns, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows([str(row.get(c) or "") for c in columns] for row in rows)


def _read_tsv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def read_lists(folder: Path = DEFAULT_FOLDER) -> list[dict]:
    """Lists with their entries: [{id, name, description, ..., entries: [...]}], checked."""
    folder = Path(folder)
    index = {row["id"]: row for row in _read_tsv(folder / "index.tsv")} if (folder / "index.tsv").exists() else {}
    ids = sorted(set(index) | {p.stem for p in folder.glob("*.tsv") if p.name != "index.tsv"})
    lists = []
    for list_id in ids:
        if not LIST_ID.match(list_id):
            raise ValueError(f"{folder}: list id {list_id!r} should be lowercase letters, digits, - and _")
        meta = index.get(list_id, {})
        path = folder / f"{list_id}.tsv"
        entries = _read_tsv(path) if path.exists() else []
        for entry in entries:
            where = f"{path}: entry {entry.get('key')!r}"
            if not entry.get("concept") and not entry.get("gloss"):
                raise ValueError(f"{where} names no concept and no gloss")
            if not entry.get("concept") and not entry.get("key"):
                entry["key"] = slug(entry["gloss"])
            if entry.get("closest") and (entry.get("relation") or "exact") not in RELATIONS:
                raise ValueError(f"{where}: unknown relation {entry.get('relation')!r}")
        lists.append({**{c: meta.get(c, "") for c in LIST_COLUMNS}, "id": list_id, "name": meta.get("name") or list_id, "entries": entries})
    return lists


def write_lists(folder: Path, lists: list[dict]) -> int:
    """Write lists (as read_lists returns them) to folder; return the number of entries written."""
    folder = Path(folder)
    _write_tsv(folder / "index.tsv", LIST_COLUMNS, sorted(lists, key=lambda l: l["id"]))
    count = 0
    for item in lists:
        entries = sorted(item["entries"], key=lambda e: (e.get("added_at") or "", e.get("key") or ""))
        _write_tsv(folder / f"{item['id']}.tsv", ENTRY_COLUMNS, entries)
        count += len(entries)
    return count


def load_lists(conn, folder: Path = DEFAULT_FOLDER) -> dict[str, int]:
    """Replace the "custom" source's rows with the lists in folder; return row counts."""
    writer = Writer(conn, SOURCE, "local")
    for item in read_lists(folder):
        node = list_node(item["id"])
        writer.concept(node, "list", item["name"])
        writer.prop(node, "description", item.get("description"))
        for entry in item["entries"]:
            member = entry.get("concept") or concept_node(entry["key"])
            if not entry.get("concept"):
                writer.concept(member, "concept", entry["gloss"])
                writer.prop(member, "definition", entry.get("definition"))
                writer.prop(member, "ontological_category", entry.get("category"))
                if entry.get("closest"):
                    writer.mapping(member, entry["closest"], entry.get("relation") or "exact")
            writer.relation(member, node, "in_list")
    return writer.finish()


def _json_files(folder: Path):
    for path in sorted(folder.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(body, dict):
            yield path, body.get("data", body) if isinstance(body.get("data"), dict) else body


def lists_from_page(folder: Path, owner_reviewer: str) -> list[dict]:
    """Lists from an export of the review page's store.

    The export holds lists/<id>.json (one per list) and lists/<id>/entries/<key>.json (its
    entries); "added_by" is `owner_reviewer` for the page owner and the viewer's opaque id otherwise.
    """
    root = Path(folder)
    root = root / "lists" if (root / "lists").is_dir() else root
    lists = []
    for path, body in _json_files(root):
        list_id = body.get("id") or path.stem
        entries = []
        for _, entry in _json_files(root / list_id / "entries"):
            if not entry.get("concept") and not entry.get("gloss"):
                continue
            entries.append({
                "key": entry.get("key") or "",
                "concept": entry.get("concept") or "",
                "gloss": entry.get("gloss") or "",
                "definition": entry.get("definition") or "",
                "category": entry.get("category") or "",
                "closest": entry.get("closest") or "",
                "relation": (entry.get("relation") or "") if entry.get("closest") else "",
                "note": entry.get("note") or "",
                "added_by": owner_reviewer if entry.get("owner") else (entry.get("by") or ""),
                "added_at": (entry.get("at") or "")[:10],
            })
        lists.append({
            "id": list_id,
            "name": body.get("name") or list_id,
            "description": body.get("description") or "",
            "created_by": owner_reviewer if body.get("owner") else (body.get("by") or ""),
            "created_at": (body.get("at") or "")[:10],
            "entries": entries,
        })
    return lists


def list_ids(folder: Path = DEFAULT_FOLDER) -> list[str]:
    """Node ids of the custom lists in folder, for the review queue."""
    return [list_node(item["id"]) for item in read_lists(folder)] if Path(folder).is_dir() else []
