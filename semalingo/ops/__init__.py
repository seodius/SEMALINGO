"""The operations library (step 6): the questions every interface (MCP server, CLI, notebooks) asks.

Six operations from the build plan, plus three helpers:

- `lookup(query)`: nodes whose name or written form is the query, in every source, with what
  each word means; a node id ("concepticon:1248") gives that node's own description.
- `neighbours(node)`: nodes linked to a node, up to a few hops, through relations and mappings.
- `norms(node)`: measured values of a node and of the words and nodes linked to it (frequency,
  age of acquisition, concreteness, borrowability, ...), each with its source and how it was reached.
- `colexifications(concept)`: concepts that languages express with the same word (CLICS) and the
  semantic shifts between them (DatSemShift).
- `path(a, b)`: the shortest connections between two nodes, with the edges used.
- `compare(a, b)`: two nodes side by side: norms, relations, shared neighbours, connection.
- `words(concept, language)`: the words languages use for a concept, from every source.
- `sources()`: loaded sources with version and licence.
- `sql(query)`: a read-only query on the core tables.

Every result carries provenance: the sources its nodes and edges come from (with version and
licence) and, for mapping edges, the method, confidence and reviewer. The SQL is plain enough
to run on DuckDB (the real database) and SQLite (the tests).
"""

from __future__ import annotations

import re
import threading
from collections import Counter, defaultdict, deque

from ..languages import ISO1_GLOTTOCODE

BATCH = 500  # ids per IN (...) list
HUB = 3000  # nodes with more edges than this are not expanded beyond the first hop
SKIP_BY_DEFAULT = ("in_list", "linked")  # list membership joins everything; Concepticon's "linked" is co-listing, not meaning
MEANING_EDGES = ("expresses", "sense_of")
ROW_LIMIT = 500
READ_ONLY = re.compile(r"^\s*(select|with|describe|show|summarize|pragma\s+table_info)\b", re.I)
WRITES = re.compile(r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import|install|load|pragma|set|call|vacuum|checkpoint)\b", re.I)
FILE_FUNCTIONS = re.compile(r"\b(read_\w+|glob|sniff_csv|parquet_\w+|read_text|read_blob)\s*\(", re.I)


def source_of(node: str) -> str:
    return node.split(":", 1)[0]


def _chunks(items, size=BATCH):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


class Graph:
    """Operations on an open DuckDB or SQLite connection to the core tables."""

    def __init__(self, conn):
        self.conn = conn
        self.lock = threading.Lock()
        self._sources = None

    # --- plumbing ------------------------------------------------------------------------
    def rows(self, sql, params=()):
        with self.lock:
            return self.conn.execute(sql, list(params)).fetchall()

    def rows_in(self, sql, ids, params_before=(), params_after=()):
        """Run sql with "{ids}" replaced by an IN list, batched; concatenate the rows."""
        out = []
        for chunk in _chunks(ids):
            marks = ", ".join("?" * len(chunk))
            out += self.rows(sql.replace("{ids}", marks), [*params_before, *chunk, *params_after])
        return out

    def source_info(self) -> dict[str, dict]:
        if self._sources is None:
            self._sources = {
                sid: {"id": sid, "name": name, "version": version, "licence": licence}
                for sid, name, version, licence in self.rows("SELECT source_id, name, version, licence FROM sources")
            }
        return self._sources

    def provenance(self, nodes=(), edges=()) -> dict:
        used = Counter(source_of(n) for n in nodes if n)
        methods = Counter()
        for e in edges:
            if e.get("source"):
                used[e["source"]] += 1
            if e.get("method"):
                methods[e["method"] + (f" by {e['reviewer']}" if e.get("reviewer") else "")] += 1
        info = self.source_info()
        sources = [info.get(s, {"id": s, "name": s, "version": None, "licence": None, "note": "not a loaded source"})
                   for s in sorted(used)]
        out = {"sources": sources}
        if methods:
            out["mapping_methods"] = dict(methods)
        return out

    def language(self, value: str | None) -> str | None:
        """A Glottocode from a Glottocode, an ISO 639-1 or 639-3 code, or a language name."""
        if not value:
            return None
        value = value.strip()
        if value.lower() in ISO1_GLOTTOCODE:
            return ISO1_GLOTTOCODE[value.lower()]
        if re.fullmatch(r"[a-z]{4}\d{4}", value):
            return value
        found = self.rows(
            "SELECT glottocode FROM languages WHERE iso639_3 = ? OR lower(name) = ? ORDER BY level = 'language' DESC LIMIT 1",
            [value.lower(), value.lower()],
        )
        return found[0][0] if found else value

    def exists(self, node: str) -> bool:
        return self.describe_nodes([node])[node]["kind"] != "external" or bool(
            self.rows("SELECT 1 FROM mappings WHERE from_id = ? OR to_id = ? LIMIT 1", [node, node]))

    def equivalents(self, node: str) -> dict[str, dict | None]:
        """The node and the nodes it is mapped to as exact or close, by import or review. Gloss
        proposals between concepts are left out (they are proposals, not facts); WordNet 3.0 and
        CILI ids only bridge and are left out too."""
        found: dict[str, dict | None] = {node: None}
        for e in self.edges([node], "both", ["mapping:exact", "mapping:close"]):
            other = e["to"] if e["from"] == node else e["from"]
            if e["method"] == "gloss" or other.startswith(("pwn30:", "cili:")):
                continue
            found.setdefault(other, e)
        return found

    def describe_nodes(self, ids) -> dict[str, dict]:
        """{id: {"id", "source", "label", "kind" | "language"}} for concept and form nodes."""
        ids = [i for i in dict.fromkeys(ids) if i]
        out = {}
        for node, source, kind, gloss in self.rows_in(
            "SELECT concept_id, source_id, kind, gloss FROM concepts WHERE concept_id IN ({ids})", ids
        ):
            out[node] = {"id": node, "source": source, "kind": kind, "label": gloss or node}
        rest = [i for i in ids if i not in out]
        for node, source, language, text in self.rows_in(
            "SELECT form_id, source_id, language, written_form FROM forms WHERE form_id IN ({ids})", rest
        ):
            out[node] = {"id": node, "source": source, "kind": "form", "label": text, "language": language}
        for node in ids:
            out.setdefault(node, {"id": node, "source": source_of(node), "kind": "external", "label": node})
        return out

    def edges(self, nodes, direction="both", edge_types=None, skip=SKIP_BY_DEFAULT) -> list[dict]:
        """Relations and mappings touching the nodes. A mapping's type is "mapping:<type>"."""
        nodes = list(dict.fromkeys(nodes))
        wanted = set(edge_types or [])
        out = []
        columns = {"both": ("from_id", "to_id"), "out": ("from_id",), "in": ("to_id",)}[direction]
        for column in columns:
            for source, a, b, kind, weight in self.rows_in(
                f"SELECT source_id, from_id, to_id, relation_type, weight FROM relations WHERE {column} IN ({{ids}})", nodes
            ):
                if (wanted and kind not in wanted) or (not wanted and kind in skip):
                    continue
                edge = {"from": a, "to": b, "type": kind, "source": source}
                if weight is not None:
                    edge["weight"] = weight
                out.append(edge)
            for a, b, kind, confidence, method, reviewer in self.rows_in(
                f"SELECT from_id, to_id, mapping_type, confidence, method, reviewer FROM mappings WHERE {column} IN ({{ids}})", nodes
            ):
                name = f"mapping:{kind}"
                if wanted and name not in wanted and "mapping" not in wanted:
                    continue
                edge = {"from": a, "to": b, "type": name, "method": method, "confidence": round(confidence, 3)}
                if reviewer:
                    edge["reviewer"] = reviewer
                out.append(edge)
        return out

    # --- lookup ----------------------------------------------------------------------------
    def lookup(self, query: str, language: str | None = None, limit: int = 25) -> dict:
        query = (query or "").strip()
        if not query:
            return {"error": "empty query"}
        if ":" in query and " " not in query and self.exists(query):
            return self.describe(query)
        variants = list(dict.fromkeys([query, query.lower(), query.upper(), query.capitalize()]))
        concepts = self.rows_in(
            "SELECT concept_id, source_id, kind, gloss FROM concepts WHERE gloss IN ({ids})", variants
        )
        # Concepticon names a sense in brackets: EYE (ORGAN)
        concepts += self.rows(
            "SELECT concept_id, source_id, kind, gloss FROM concepts WHERE gloss LIKE ? LIMIT 200", [query.upper() + " (%"]
        )
        glottocode = self.language(language)
        forms = self.rows_in(
            "SELECT form_id, source_id, language, written_form FROM forms WHERE written_form IN ({ids})"
            + (" AND language = ?" if glottocode else ""),
            variants, params_after=[glottocode] if glottocode else [],
        )
        # what the words mean: the concepts they express or are matched to
        meanings: dict[str, list] = defaultdict(list)
        form_ids = [f[0] for f in forms]
        for edge in self.edges(form_ids, "out", list(MEANING_EDGES) + ["mapping"]):
            meanings[edge["from"]].append(edge)
        labels = self.describe_nodes([e["to"] for es in meanings.values() for e in es])
        groups: dict[tuple, dict] = {}
        for form, source, lang, text in forms:
            key = (source, lang)
            group = groups.setdefault(key, {"source": source, "language": lang, "forms": 0, "examples": [], "means": Counter()})
            group["forms"] += 1
            if len(group["examples"]) < 3:
                group["examples"].append(form)
            for e in meanings.get(form, []):
                group["means"][e["to"]] += 1
        words = []
        for group in sorted(groups.values(), key=lambda g: (-sum(g["means"].values()), g["source"])):
            means = [{**labels[n], "words": c} for n, c in group["means"].most_common(5)]
            words.append({k: v for k, v in {**group, "means": means}.items()})
        found = [{"id": c, "source": s, "kind": k, "label": g} for c, s, k, g in dict.fromkeys(concepts)]
        found.sort(key=lambda n: (n["label"].upper() != query.upper(), n["source"], n["label"]))
        return {
            "query": query,
            "language": glottocode,
            "concepts": found[:limit],
            "concepts_total": len(found),
            "words": words[:limit],
            "words_total": len(forms),
            "provenance": self.provenance([n["id"] for n in found[:limit]] + [w["examples"][0] for w in words[:limit]]),
        }

    def describe(self, node: str) -> dict:
        """One node: what it is, its own properties, and its edges counted by type."""
        info = self.describe_nodes([node])[node]
        props = [
            {"property": p, "value": n if n is not None else t, "source": s}
            for p, n, t, s in self.rows(
                "SELECT property, value_num, value_text, source_id FROM properties WHERE node_id = ? ORDER BY source_id, property", [node]
            )
        ]
        edges = self.edges([node], "both", skip=())
        counts = Counter((e["type"], "out" if e["from"] == node else "in") for e in edges)
        mappings = [e for e in edges if e["type"].startswith("mapping:")][:30]
        labels = self.describe_nodes([e["to"] if e["from"] == node else e["from"] for e in mappings])
        for e in mappings:
            other = e["to"] if e["from"] == node else e["from"]
            e["other"] = labels[other]
        return {
            "node": info,
            "properties": props[:60],
            "edge_counts": [{"type": t, "direction": d, "count": n} for (t, d), n in counts.most_common()],
            "mappings": mappings,
            "provenance": self.provenance([node], mappings),
        }

    # --- neighbours ------------------------------------------------------------------------
    def neighbours(self, node: str, hops: int = 1, edge_types=None, direction: str = "both",
                   language: str | None = None, limit: int = 50) -> dict:
        hops = max(1, min(int(hops), 4))
        glottocode = self.language(language)
        seen = {node: None}
        frontier = [node]
        reached = []
        counts = Counter()
        skipped_hubs = []
        for hop in range(1, hops + 1):
            edges = self.edges(frontier, direction, edge_types)
            degree = Counter(e["from"] if e["from"] in frontier else e["to"] for e in edges)
            hubs = {n for n, d in degree.items() if d > HUB and hop < hops and n != node}
            skipped_hubs += sorted(hubs)
            new = []
            for e in edges:
                here = e["from"] if e["from"] in seen else e["to"]
                other = e["to"] if here == e["from"] else e["from"]
                if other in seen:
                    continue
                seen[other] = e
                counts[(hop, e["type"])] += 1
                new.append(other)
                reached.append((hop, other, e))
            frontier = [n for n in new if n not in hubs]
            if not frontier:
                break
        labels = self.describe_nodes([n for _, n, _ in reached[: limit * 20]])
        nodes = []
        for hop, other, edge in reached:
            info = labels.get(other) or {"id": other, "source": source_of(other), "label": other}
            if glottocode and info.get("kind") == "form" and info.get("language") != glottocode:
                continue
            nodes.append({**info, "hop": hop, "edge": edge})
            if len(nodes) >= limit:
                break
        return {
            "node": self.describe_nodes([node])[node],
            "nodes": nodes,
            "total": len(reached),
            "counts": [{"hop": h, "type": t, "count": n} for (h, t), n in sorted(counts.items())],
            "skipped_hubs": skipped_hubs[:20],
            "provenance": self.provenance([node] + [n["id"] for n in nodes], [n["edge"] for n in nodes]),
        }

    # --- norms ---------------------------------------------------------------------------
    PREFERRED = ("aoa", "frequency", "concreteness", "familiarity", "imageability", "valence", "arousal", "dominance",
                 "borrowability", "age", "simplicity", "iconicity", "sensory modality")

    def norms(self, node: str, constructs=None, language: str | None = None, per_construct: int = 2, limit: int = 80) -> dict:
        """Values measured on the node, on nodes mapped to it (imported or reviewed), and on words that
        express it or are matched to it. Without `constructs`, a few values of each common construct
        (PREFERRED) and a count of every construct; with it, every value of those constructs (a
        construct name or part of a property name)."""
        glottocode = self.language(language)
        via = self.equivalents(node)
        level1 = list(via)
        for e in self.edges(level1, "in", list(MEANING_EDGES) + ["mapping:exact", "mapping:close"]):
            via.setdefault(e["from"], e)
        types = {
            (s, p): {"construct": c, "statistic": st, "language": l, "description": d}
            for s, p, c, st, l, d in self.rows(
                "SELECT source_id, property, construct, statistic, language, description FROM property_types"
            )
        }
        wanted = [c.lower() for c in constructs or []]
        level2 = [n for n in via if n not in level1]
        props = self.rows_in(
            "SELECT node_id, source_id, property, value_num, value_text FROM properties WHERE node_id IN ({ids})", level1
        ) + self.rows_in(
            "SELECT node_id, source_id, property, value_num, value_text FROM properties WHERE node_id IN ({ids}) AND value_num IS NOT NULL",
            level2,
        )
        labels = self.describe_nodes({p[0] for p in props})
        rows = []
        for n, source, prop, num, text in props:
            info = labels[n]
            if glottocode and info.get("kind") == "form" and info.get("language") != glottocode:
                continue
            meta = types.get((source, prop), {})
            construct = meta.get("construct") or ("description" if prop in ("definition", "gloss", "documentation") else "other")
            if wanted and not any(w in construct.lower() or w in prop.lower() for w in wanted):
                continue
            row = {"construct": construct, "value": num if num is not None else text, "property": prop, "source": source,
                   "on": info["label"] + (f" ({info['language']})" if info.get("language") else ""), "node": n}
            if meta.get("statistic"):
                row["statistic"] = meta["statistic"]
            if meta.get("language") or info.get("language"):
                row["language"] = meta.get("language") or info.get("language")
            if via[n]:
                e = via[n]
                row["via"] = f"{e['type']} {e['to'] if e['from'] == n else e['from']}" + (
                    f" ({e['method']}, {e['confidence']})" if e.get("method") else "")
            rows.append(row)
        order = {c: i for i, c in enumerate(self.PREFERRED)}
        first = ("stan1293", "dutc1256")  # English and Dutch values first within a construct
        rows.sort(key=lambda r: (order.get(r["construct"], len(order)), r["construct"], r.get("language") not in first,
                                 r.get("language") or "", r.get("statistic") not in ("mean", "zipf", None), r["source"], r["property"]))
        counts = Counter(r["construct"] for r in rows)
        if not wanted:  # a few values of the common constructs; the rest are counted
            shown, taken = [], Counter()
            for r in rows:
                if r["construct"] in order and taken[r["construct"]] < per_construct:
                    shown.append(r)
                    taken[r["construct"]] += 1
            rows_out = shown[:limit]
        else:
            rows_out = rows[:limit]
        return {
            "node": self.describe_nodes([node])[node],
            "values": rows_out,
            "total": len(rows),
            "constructs": dict(counts.most_common()),
            "note": "ask again with constructs=[...] for every value of a construct",
            "provenance": self.provenance([r["node"] for r in rows_out], [via[r["node"]] for r in rows_out if via.get(r["node"])]),
        }

    # --- colexifications -------------------------------------------------------------------
    def concepticon_of(self, node: str) -> str | None:
        if node.startswith("concepticon:"):
            return node
        for (target,) in self.rows(
            "SELECT to_id FROM mappings WHERE from_id = ? AND to_id LIKE 'concepticon:%' AND mapping_type IN ('exact', 'close') "
            "ORDER BY confidence DESC LIMIT 1", [node]
        ):
            return target
        return None

    def mapped_from(self, concept: str, source: str) -> list[str]:
        return [n for (n,) in self.rows(
            "SELECT from_id FROM mappings WHERE to_id = ? AND from_id LIKE ? AND mapping_type = 'exact'", [concept, source + ":%"]
        )]

    def colexifications(self, concept: str, limit: int = 25) -> dict:
        target = self.concepticon_of(concept) or concept
        out = {"concept": self.describe_nodes([target])[target], "clics": [], "datsemshift": []}
        edges_used = []
        clics = self.mapped_from(target, "clics") or ([concept] if concept.startswith("clics:") else [])
        partners = []
        for e in self.edges(clics, "both", ["colexification"]):
            other = e["to"] if e["from"] in clics else e["from"]
            partners.append((other, e))
        shifts = []
        dss = self.mapped_from(target, "datsemshift") or ([concept] if concept.startswith("datsemshift:") else [])
        for e in self.edges(dss, "both", ["shift_polysemy", "shift_derivation"]):
            other = e["to"] if e["from"] in dss else e["from"]
            shifts.append((other, e, "to" if e["from"] in dss else "from"))
        back = {}
        for n in {o for o, _ in partners} | {o for o, _, _ in shifts}:
            back[n] = self.concepticon_of(n) or n
        labels = self.describe_nodes(list(back.values()) + list(back))
        for other, e in sorted(partners, key=lambda p: -(p[1].get("weight") or 0))[:limit]:
            c = back[other]
            out["clics"].append({"concept": c, "label": labels[c]["label"], "families": int(e.get("weight") or 0)})
            edges_used.append(e)
        for other, e, way in sorted(shifts, key=lambda s: -(s[1].get("weight") or 0))[:limit]:
            c = back[other]
            out["datsemshift"].append({"concept": c, "label": labels[c]["label"], "kind": e["type"].replace("shift_", ""),
                                       "direction": way, "families": int(e.get("weight") or 0)})
            edges_used.append(e)
        out["note"] = ("clics: concepts expressed by one word in the given number of language families; "
                       "datsemshift: attested semantic shifts (polysemy or derivation), 'to' = from this concept to the other")
        out["provenance"] = self.provenance([target] + clics + dss, edges_used)
        return out

    # --- path ------------------------------------------------------------------------------
    def path(self, a: str, b: str, max_hops: int = 4, edge_types=None, paths: int = 3) -> dict:
        """Shortest undirected connections between two nodes (breadth-first from both ends)."""
        max_hops = max(1, min(int(max_hops), 6))
        parents = ({a: None}, {b: None})  # node -> (previous node, edge) per side
        frontiers = ([a], [b])
        meet = []
        hops = 0
        while hops < max_hops and not meet and frontiers[0] and frontiers[1]:
            side = 0 if len(frontiers[0]) <= len(frontiers[1]) else 1
            mine, theirs = parents[side], parents[1 - side]
            edges = self.edges(frontiers[side], "both", edge_types)
            degree = Counter(e["from"] if e["from"] in mine else e["to"] for e in edges)
            new = []
            for e in edges:
                here = e["from"] if e["from"] in mine else e["to"]
                other = e["to"] if here == e["from"] else e["from"]
                if other in mine:
                    continue
                mine[other] = (here, e)
                new.append(other)
                if other in theirs:
                    meet.append(other)
            frontiers = (new, frontiers[1]) if side == 0 else (frontiers[0], new)
            frontiers = tuple([n for n in f if degree.get(n, 0) <= HUB or n in (a, b)] for f in frontiers)
            hops += 1

        def walk(node, side):
            steps = []
            while parents[side][node] is not None:
                prev, edge = parents[side][node]
                steps.append(edge)
                node = prev
            return steps

        found = []
        for node in dict.fromkeys(meet):
            left = list(reversed(walk(node, 0)))
            right = walk(node, 1)
            found.append(left + right)
            if len(found) >= paths:
                break
        ids = {n for p in found for e in p for n in (e["from"], e["to"])} | {a, b}
        labels = self.describe_nodes(ids)

        def route(edges):
            nodes = [a]
            for e in edges:
                nodes.append(e["to"] if e["from"] == nodes[-1] else e["from"])
            return [f"{labels[n]['label']} [{n}]" if labels[n]["label"] != n else n for n in nodes]

        return {
            "from": labels[a],
            "to": labels[b],
            "paths": [{"length": len(p), "route": route(p),
                       "edges": [{**e, "from_label": labels[e["from"]]["label"], "to_label": labels[e["to"]]["label"]} for e in p]}
                      for p in found],
            "searched_hops": hops,
            "provenance": self.provenance(ids, [e for p in found for e in p]),
        }

    # --- compare ---------------------------------------------------------------------------
    def compare(self, a: str, b: str) -> dict:
        sides = {}
        neighbours = {}
        for node in (a, b):
            edges = self.edges([node], "both")
            neighbours[node] = {e["to"] if e["from"] == node else e["from"]: e for e in edges}
            norms = self.norms(node, per_construct=2, limit=60)["values"]
            summary: dict[str, list] = defaultdict(list)
            for row in norms:
                summary[row["construct"]].append({k: row[k] for k in ("value", "source", "property", "language") if k in row})
            sides[node] = {
                "node": self.describe_nodes([node])[node],
                "edge_counts": dict(Counter(e["type"] for e in edges).most_common(15)),
                "norms": dict(summary),
            }
        shared = sorted(set(neighbours[a]) & set(neighbours[b]) - {a, b})
        labels = self.describe_nodes(shared[:40])
        connection = self.path(a, b, max_hops=3, paths=1)["paths"]
        colex = None
        ca, cb = self.concepticon_of(a), self.concepticon_of(b)
        if ca and cb:
            for item in self.colexifications(ca, limit=1000)["clics"]:
                if item["concept"] == cb:
                    colex = item["families"]
        return {
            "a": sides[a],
            "b": sides[b],
            "shared_neighbours": [{**labels[n], "edge_a": neighbours[a][n]["type"], "edge_b": neighbours[b][n]["type"]} for n in shared[:40]],
            "shared_total": len(shared),
            "connection": connection[0] if connection else None,
            "colexified_in_families": colex,
            "provenance": self.provenance([a, b] + shared[:40]),
        }

    # --- words -----------------------------------------------------------------------------
    def words(self, concept: str, language: str | None = None, limit: int = 25) -> dict:
        """The words languages use for a concept: written words that express it or are matched to it,
        directly or through a node mapped to it (Lexibank's, NoRaRe's, WOLD's, WordNet's concept)."""
        glottocode = self.language(language)
        holders = self.equivalents(concept)
        found = []
        for e in self.edges(list(holders), "in", list(MEANING_EDGES) + ["mapping:exact", "mapping:close"]):
            found.append((e["from"], e, holders.get(e["to"])))
        ids = [f for f, _, _ in found]
        info = self.describe_nodes(ids)
        by_language: dict[str, list] = defaultdict(list)
        for form, edge, hop in found:
            node = info[form]
            if node.get("kind") != "form":
                continue
            if glottocode and node.get("language") != glottocode:
                continue
            if node["label"] in ("<NA>", "") or (glottocode is None and node["source"] == "concepticon-maps"):
                continue  # empty glosses; lookup-table keys repeat the list glosses
            by_language[node["language"]].append({"word": node["label"], "source": node["source"], "form": form,
                                                  **({"phonetic": True} if node["source"] == "lexibank" else {}),
                                                  "via": hop["to"] if hop and hop["from"] == concept else (hop["from"] if hop else None),
                                                  **({"match": edge["confidence"]} if edge["type"].startswith("mapping:") else {})})
        names = dict(self.rows_in("SELECT glottocode, name FROM languages WHERE glottocode IN ({ids})", list(by_language)))
        out = []
        for lang, items in sorted(by_language.items(), key=lambda kv: -len(kv[1])):
            distinct = Counter(i["word"].casefold() for i in items)
            example = {}
            for i in items:
                example.setdefault(i["word"].casefold(), i)
            out.append({
                "language": lang, "name": names.get(lang, lang), "forms": len(items),
                "words": [{**example[w], "sources": n} for w, n in distinct.most_common(8)],
            })
        return {
            "concept": self.describe_nodes([concept])[concept],
            "languages": out[: (limit if not glottocode else 1)],
            "languages_total": len(out),
            "provenance": self.provenance([concept] + [w["form"] for l in out[:limit] for w in l["words"][:2]],
                                          [h for h in holders.values() if h]),
        }

    # --- sources and sql -------------------------------------------------------------------
    def sources(self) -> dict:
        return {"sources": sorted(self.source_info().values(), key=lambda s: s["id"])}

    def sql(self, query: str, limit: int = 200) -> dict:
        """A read-only query: one SELECT/WITH/DESCRIBE statement, no file or network functions."""
        text = (query or "").strip().rstrip(";")
        if not READ_ONLY.match(text) or ";" in text or WRITES.search(re.sub(r"'[^']*'", "''", text)) \
                or FILE_FUNCTIONS.search(text):
            return {"error": "only a single read-only SELECT, WITH or DESCRIBE statement on the core tables is allowed"}
        limit = max(1, min(int(limit), ROW_LIMIT))
        with self.lock:
            cursor = self.conn.execute(text)
            columns = [d[0] for d in cursor.description or []]
            rows = cursor.fetchmany(limit + 1)
        return {"columns": columns, "rows": [list(r) for r in rows[:limit]], "truncated": len(rows) > limit}


# The operations as functions on a connection, for notebooks: ops.lookup(conn, "eye")
def lookup(conn, query: str, **options) -> dict:
    return Graph(conn).lookup(query, **options)


def neighbours(conn, node: str, **options) -> dict:
    return Graph(conn).neighbours(node, **options)


def norms(conn, node: str, **options) -> dict:
    return Graph(conn).norms(node, **options)


def colexifications(conn, concept: str, **options) -> dict:
    return Graph(conn).colexifications(concept, **options)


def path(conn, a: str, b: str, **options) -> dict:
    return Graph(conn).path(a, b, **options)


def compare(conn, a: str, b: str) -> dict:
    return Graph(conn).compare(a, b)


def words(conn, concept: str, **options) -> dict:
    return Graph(conn).words(concept, **options)


__all__ = ["Graph", "lookup", "neighbours", "norms", "colexifications", "path", "compare", "words"]
