"""Review of mapping proposals (step 4, pass 3) and checks on the mapping layer.

- `review_queue`: the proposals for a priority set of Concepticon concept sets, with what a
  reviewer needs to decide (definitions, lemmas, the SUMO term behind each synset).
- `review_payload`: the queue plus, per concept set, how other languages express it
  (semalingo.usage), the SUMO and WordNet hierarchies and relations around it
  (semalingo.context), and a catalogue of all Concepticon concept sets to add to custom lists
  (semalingo.lists): what the review page shows.
- `load_reviewed`: reviewed decisions from mappings/*.tsv become "manual" mappings that name
  their reviewer. The TSV files are the source of truth for reviewed edges; they live in the
  repository so others can see, reuse and correct them.
- `check`: quality checks on the mapping layer.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .writer import COLUMNS, bulk_insert, dedupe, is_duckdb

# The columns of mappings/<from source>__<to source>.tsv (see mappings/README.md).
REVIEW_COLUMNS = ("from_id", "to_id", "mapping_type", "confidence", "method", "reviewer", "reviewed_at", "note")
MAPPING_TYPES = ("exact", "close", "broader", "narrower", "related")
METHODS = ("manual", "llm", "gloss")
# Concept lists that define the first review batch, in review order.
DEFAULT_LISTS = (
    "Goddard-2011-63",      # NSM semantic primes
    "Swadesh-1955-100",
    "Tadmor-2009-100",      # Leipzig-Jakarta list
    "Ogden-1930-100",       # Basic English operations
    "Ogden-1930-200",       # Basic English picturable things
    "Swadesh-1952-200",
    "Luniewska-2019-299",   # early-acquired words, 29 languages
    "widely-used:50",       # concept sets that at least 50 Concepticon lists use
    "basic-english:words",  # Ogden's 850 Basic English words, matched to concept sets by gloss
)
# Lists that are not Concepticon lists: "widely-used:<n>" and "<word-list source>:words".
WIDELY_USED = "widely-used:"
WORDS = ":words"


def list_members(conn, list_id: str) -> dict[str, dict | None]:
    """The concepts in a list: {concept: None}, or {concept: {"word", "share"}} for a word list.

    - "Swadesh-1955-100": a Concepticon list; "custom:list/core": any list node;
    - "widely-used:50": concept sets that at least 50 Concepticon concept lists use;
    - "basic-english:words": the words of a loaded word list, each as the concept set it is
      best matched to (a reviewed mapping first, else the gloss match with the largest share).
    """
    if list_id.startswith(WIDELY_USED):
        least = int(list_id[len(WIDELY_USED):])
        return {
            concept: None
            for concept, n in _rows(
                conn,
                "SELECT from_id, COUNT(*) FROM relations WHERE source_id = 'concepticon' AND relation_type = 'in_list' "
                "AND from_id NOT LIKE 'concepticon:gloss/%' AND to_id LIKE 'concepticon:list/%' GROUP BY from_id",
            )
            if n >= least
        }
    if list_id.endswith(WORDS):
        return word_list_choices(conn, list_id[: -len(WORDS)])[0]
    return {
        concept: None
        for (concept,) in _rows(
            conn,
            "SELECT from_id FROM relations WHERE source_id IN ('concepticon', 'custom') AND relation_type = 'in_list' "
            "AND to_id = ? AND from_id NOT LIKE '%:gloss/%'",
            list_node(list_id),
        )
    }


# Which ontological categories suit each category of a word list's words. A gloss match outside
# them is set aside ("mine" is a pit, not MY), unless the concept set is named by the word itself.
WORD_CATEGORY_FIT = {
    "basic-english": {
        "things (picturable)": {"Person/Thing", "Classifier"},
        "things (general)": {"Person/Thing", "Action/Process"},
        "qualities (general)": {"Property", "Number"},
        "qualities (opposites)": {"Property", "Number"},
    },
}


def word_list_choices(conn, source: str) -> tuple[dict[str, dict], list[str]]:
    """Each word of a loaded word list as one concept set, and the words left without one.

    A reviewed (manual) mapping comes first; otherwise the gloss match with the largest share
    whose ontological category suits the word's category in the list (WORD_CATEGORY_FIT), or
    whose name is the word itself; a word without any gloss match falls back on a suitable concept
    set named by the word (share 0). Returns ({concept: {"word", "share"}}, [unmatched words]).
    """
    fit = WORD_CATEGORY_FIT.get(source, {})
    category = dict(_rows(conn, "SELECT node_id, value_text FROM properties WHERE source_id = 'concepticon' AND property = 'ontological_category'"))
    gloss = dict(_rows(conn, "SELECT concept_id, gloss FROM concepts WHERE source_id = 'concepticon'"))
    words = {
        form: (word, kind)
        for form, word, kind in _rows(
            conn,
            "SELECT f.form_id, f.written_form, p.value_text FROM forms f LEFT JOIN properties p "
            "ON p.node_id = f.form_id AND p.source_id = f.source_id AND p.property = 'category' WHERE f.source_id = ?",
            source,
        )
    }
    best: dict[str, tuple] = {}  # form -> (manual first, suits the word, share, concept, word)
    for form, concept, confidence, method in _rows(
        conn,
        "SELECT m.from_id, m.to_id, m.confidence, m.method FROM mappings m JOIN forms f ON f.form_id = m.from_id "
        "WHERE f.source_id = ? AND m.method IN ('gloss', 'manual') AND m.to_id LIKE 'concepticon:%'",
        source,
    ):
        word, kind = words[form]
        allowed = fit.get(kind)
        fits = not allowed or category.get(concept) in allowed
        named = (gloss.get(concept) or "").split(" (")[0] == word.upper()
        if method != "manual" and not fits and not named:
            continue
        # a suitable category beats a mere name: "watch" (a thing) is WRISTWATCH before WATCH (look)
        rank = (1 if method == "manual" else 0, 1 if fits else 0, confidence or 0.0, concept, word)
        if form not in best or rank > best[form]:
            best[form] = rank
    # a word that no gloss matches may still name a concept set ("almost" is ALMOST); take the most listed
    named: dict[str, list[str]] = defaultdict(list)
    for concept, name in gloss.items():
        named[name.split(" (")[0]].append(concept)
    listed = dict(_rows(
        conn,
        "SELECT from_id, COUNT(*) FROM relations WHERE source_id = 'concepticon' AND relation_type = 'in_list' "
        "AND from_id NOT LIKE 'concepticon:gloss/%' GROUP BY from_id",
    ))
    for form, (word, kind) in words.items():
        if form in best:
            continue
        allowed = fit.get(kind)
        options = [c for c in named.get(word.upper(), []) if not allowed or category.get(c) in allowed]
        if options:
            best[form] = (0, 1, 0.0, max(options, key=lambda c: listed.get(c, 0)), word)
    members: dict[str, dict] = {}
    for manual, _, share, concept, word in sorted(best.values(), key=lambda b: (-b[0], -b[1], -b[2], b[4])):
        if concept not in members:
            members[concept] = {"word": word, "share": 1.0 if manual else round(share, 3)}
    unmatched = sorted(word for form, (word, _) in words.items() if form not in best)
    return members, unmatched


def unmatched_words(conn, source: str) -> list[str]:
    """Words of a loaded word list that no suitable concept set is matched to."""
    return word_list_choices(conn, source)[1]


def _rows(conn, sql, *params):
    return conn.execute(sql, list(params)).fetchall()


def list_node(list_id: str) -> str:
    """A Concepticon list id ("Swadesh-1955-100") or any list's node id ("custom:list/core") as a node id."""
    return list_id if ":" in list_id else f"concepticon:list/{list_id}"


def review_queue(conn, concept_lists=DEFAULT_LISTS, top: int = 5) -> list[dict]:
    """Concepts in the given lists (Concepticon lists or custom lists) with their WordNet proposals."""
    order: dict[str, tuple[int, list[str]]] = {}
    via: dict[str, dict] = defaultdict(dict)  # concept -> {word list: {"word", "share"}}
    for rank, list_id in enumerate(concept_lists):
        for concept, word in list_members(conn, list_id).items():
            first, lists = order.get(concept, (rank, []))
            lists.append(list_id)
            order[concept] = (min(first, rank), lists)
            if word:
                via[concept][list_id] = word

    gloss = dict(_rows(conn, "SELECT concept_id, gloss FROM concepts WHERE source_id IN ('concepticon', 'oewn', 'custom')"))
    props: dict[str, dict] = defaultdict(dict)
    for node, prop, value in _rows(
        conn,
        "SELECT node_id, property, value_text FROM properties WHERE (source_id IN ('concepticon', 'custom') AND property IN "
        "('definition', 'ontological_category', 'semantic_field')) OR (source_id = 'oewn' AND property IN ('definition', 'pos') "
        "AND node_id NOT LIKE 'oewn:entry/%')",
    ):
        props[node][prop] = value
    proposals: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for concept, synset, confidence in _rows(
        conn,
        "SELECT from_id, to_id, confidence FROM mappings WHERE method = 'gloss' AND (from_id LIKE 'concepticon:%' "
        "OR from_id LIKE 'custom:%') AND to_id LIKE 'oewn:%'",
    ):
        proposals[concept].append((synset, confidence))
    wanted = {s for c in order for s, _ in proposals.get(c, [])}
    lemmas: dict[str, list[str]] = defaultdict(list)
    for synset, lemma in _rows(
        conn,
        "SELECT r.to_id, f.written_form FROM relations r JOIN forms f ON f.form_id = r.from_id "
        "WHERE r.source_id = 'oewn' AND r.relation_type = 'sense_of' ORDER BY r.weight",
    ):
        if synset in wanted and lemma not in lemmas[synset]:
            lemmas[synset].append(lemma)
    sumo = _sumo_terms(conn, wanted)

    queue = []
    for concept, (rank, lists) in sorted(order.items(), key=lambda item: (item[1][0], gloss.get(item[0], ""))):
        candidates = sorted(proposals.get(concept, []), key=lambda p: -p[1])[:top]
        queue.append({
            "concept": concept,
            "gloss": gloss.get(concept, ""),
            "definition": props[concept].get("definition", ""),
            "category": props[concept].get("ontological_category", ""),
            "field": props[concept].get("semantic_field", ""),
            "lists": lists,
            **({"via": via[concept]} if concept in via else {}),
            "candidates": [
                {
                    "synset": synset,
                    "pos": props[synset].get("pos", ""),
                    "lemmas": lemmas.get(synset, [gloss.get(synset, "")])[:8],
                    "definition": props[synset].get("definition", ""),
                    "confidence": round(confidence, 3),
                    "sumo": sumo.get(synset, []),
                }
                for synset, confidence in candidates
            ],
        })
    return queue


def review_payload(conn, concept_lists=DEFAULT_LISTS, top: int = 5) -> dict:
    """The review queue as the review page reads it: each concept set with its words in other
    languages and its Concepticon relations, the SUMO and WordNet hierarchies and relations of
    every candidate synset, and the catalogue of concept sets."""
    from .context import concept_relations, sumo_context, wordnet_context
    from .usage import concept_usage

    queue = review_queue(conn, concept_lists, top)
    concepts = [item["concept"] for item in queue]
    usage = concept_usage(conn, concepts)
    relations = concept_relations(conn, concepts)
    synsets, terms = set(), set()
    for item in queue:
        item["usage"] = usage["concepts"][item["concept"]]
        if relations.get(item["concept"]):
            item["relations"] = relations[item["concept"]]
        for candidate in item["candidates"]:
            synsets.add(candidate["synset"])
            terms.update(term[:-1] for term in candidate["sumo"])  # "Eye=" -> Eye
    return {
        "languages": usage["languages"],
        "items": queue,
        "catalog": catalog(conn),
        "sumo": sumo_context(conn, terms),
        "wordnet": wordnet_context(conn, synsets),
    }


def catalog(conn, definition_length: int = 160) -> list[list[str]]:
    """Every Concepticon concept set as [local id, gloss, category, definition], for finding one by name."""
    props: dict[str, dict] = defaultdict(dict)
    for node, prop, value in _rows(
        conn,
        "SELECT node_id, property, value_text FROM properties WHERE source_id = 'concepticon' "
        "AND property IN ('definition', 'ontological_category')",
    ):
        props[node][prop] = value or ""
    rows = []
    for node, gloss in _rows(conn, "SELECT concept_id, gloss FROM concepts WHERE source_id = 'concepticon' AND kind = 'concept'"):
        definition = props[node].get("definition", "")
        if len(definition) > definition_length:
            definition = definition[: definition_length - 1].rsplit(" ", 1)[0] + "…"
        rows.append([node.split(":", 1)[1], gloss or "", props[node].get("ontological_category", ""), definition])
    return sorted(rows, key=lambda r: r[1])


def _sumo_terms(conn, synsets: set[str]) -> dict[str, list[str]]:
    """SUMO terms for OEWN synsets, through CILI: oewn -> cili -> pwn30 <- sumo ("Eye=", "Organ+")."""
    if not synsets:
        return {}
    marks = {"exact": "=", "narrower": "+"}
    found: dict[str, list[str]] = defaultdict(list)
    for synset, term, kind in _rows(
        conn,
        "SELECT o.from_id, s.from_id, s.mapping_type FROM mappings o "
        "JOIN mappings c ON c.from_id = o.to_id AND c.from_id LIKE 'cili:%' "
        "JOIN mappings s ON s.to_id = c.to_id AND s.from_id LIKE 'sumo:%' "
        "WHERE o.from_id LIKE 'oewn:%' AND o.method = 'imported'",
    ):
        if synset in synsets:
            found[synset].append(term.split(":", 1)[1] + marks.get(kind, "?"))
    return found


def write_review_file(path: Path, decisions: list[dict]) -> int:
    """Write reviewed decisions (dicts with REVIEW_COLUMNS) to a TSV, sorted, one edge per line."""
    rows = sorted((tuple(str(d.get(c) or "") for c in REVIEW_COLUMNS) for d in decisions))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(REVIEW_COLUMNS)
        writer.writerows(rows)
    return len(rows)


def decisions_to_rows(decisions: list[dict], owner_reviewer: str) -> tuple[list[dict], list[dict]]:
    """Turn review-page decisions into mapping rows and "no WordNet equivalent" rows.

    A decision is {concept, synset, type, note, by, owner, at}; the reviewer is `owner_reviewer`
    for the artifact's owner and the opaque viewer id otherwise.
    """
    edges, unmatched = [], []
    for d in decisions:
        reviewer = owner_reviewer if d.get("owner") else (d.get("by") or "")
        day = (d.get("at") or "")[:10]
        if d.get("type") == "none" or not d.get("synset"):
            unmatched.append({"from_id": d["concept"], "target_source": "oewn", "reviewer": reviewer,
                              "reviewed_at": day, "note": d.get("note") or ""})
        elif d.get("type") in MAPPING_TYPES:
            edges.append({"from_id": d["concept"], "to_id": d["synset"], "mapping_type": d["type"], "confidence": 1.0,
                          "method": "manual", "reviewer": reviewer, "reviewed_at": day, "note": d.get("note") or ""})
    return edges, unmatched


UNMATCHED_COLUMNS = ("from_id", "target_source", "reviewer", "reviewed_at", "note")


def write_unmatched_file(path: Path, rows: list[dict]) -> int:
    """Concepts a reviewer found no equivalent for in the target source."""
    rows = sorted(tuple(str(r.get(c) or "") for c in UNMATCHED_COLUMNS) for r in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(UNMATCHED_COLUMNS)
        writer.writerows(rows)
    return len(rows)


def read_unmatched(paths) -> set[str]:
    found = set()
    for path in paths:
        with open(path, encoding="utf-8", newline="") as handle:
            found |= {row["from_id"] for row in csv.DictReader(handle, delimiter="\t")}
    return found


def read_review_files(paths) -> list[dict]:
    decisions = []
    for path in paths:
        with open(path, encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row.get("mapping_type") not in MAPPING_TYPES:
                    raise ValueError(f"{path}: unknown mapping type {row.get('mapping_type')!r} for {row.get('from_id')}")
                row["method"] = row.get("method") or "manual"
                if row["method"] not in METHODS:
                    raise ValueError(f"{path}: unknown method {row['method']!r} for {row.get('from_id')}")
                if row["method"] == "manual" and not row.get("reviewer"):
                    raise ValueError(f"{path}: {row.get('from_id')} -> {row.get('to_id')} names no reviewer")
                decisions.append(row)
    return decisions


def load_reviewed(conn, paths) -> int:
    """Replace the manual and LLM mappings with the edges in the given TSV files."""
    decisions = read_review_files(paths)
    rows = [
        (d["from_id"], d["to_id"], d["mapping_type"], float(d.get("confidence") or 1.0), d["method"], d.get("reviewer") or None)
        for d in decisions
    ]
    conn.execute("DELETE FROM mappings WHERE method IN ('manual', 'llm')")
    bulk_insert(conn, "mappings", COLUMNS["mappings"], dedupe("mappings", rows))
    if not is_duckdb(conn):
        conn.commit()
    return len(rows)


def check(conn, concept_lists=DEFAULT_LISTS, unmatched: set[str] | None = None) -> list[str]:
    """Quality checks on the Concepticon -> WordNet layer, as report lines.

    `unmatched`: concepts a reviewer marked as having no WordNet equivalent.
    """
    unmatched = unmatched or set()
    lines = []
    proposals = _rows(
        conn,
        "SELECT from_id, to_id, confidence FROM mappings WHERE method = 'gloss' AND from_id LIKE 'concepticon:%' AND to_id LIKE 'oewn:%'",
    )
    best: dict[str, tuple[str, float]] = {}
    second: dict[str, float] = {}
    for concept, synset, confidence in proposals:
        if concept not in best or confidence > best[concept][1]:
            if concept in best:
                second[concept] = max(second.get(concept, 0.0), best[concept][1])
            best[concept] = (synset, confidence)
        else:
            second[concept] = max(second.get(concept, 0.0), confidence)
    concepts = {c for (c,) in _rows(conn, "SELECT concept_id FROM concepts WHERE source_id = 'concepticon' AND kind = 'concept'")}
    reviewed = defaultdict(list)
    for concept, synset, kind in _rows(
        conn, "SELECT from_id, to_id, mapping_type FROM mappings WHERE method = 'manual' AND from_id LIKE 'concepticon:%'"
    ):
        reviewed[concept].append((synset, kind))

    decided = set(reviewed) | unmatched
    unmapped = concepts - set(best) - decided
    lines.append(f"concept sets: {len(concepts)}; with a WordNet proposal: {len(best)}; reviewed: {len(reviewed)} linked, "
                 f"{len(unmatched & concepts)} with no WordNet equivalent; no proposal and not reviewed: {len(unmapped)}")
    unclear = sum(1 for c, (_, conf) in best.items() if conf < 1.5 * second.get(c, 0.0))
    lines.append(f"proposals whose best candidate is not clearly ahead of the second (ratio < 1.5): {unclear}")
    shared = Counter(synset for synset, _ in best.values())
    crowded = [(s, n) for s, n in shared.most_common() if n > 2][:10]
    lines.append("synsets proposed as best for more than two concept sets: "
                 + (", ".join(f"{s.split(':')[1]} ({n})" for s, n in crowded) or "none"))
    exact_by_synset = defaultdict(list)
    for concept, edges in reviewed.items():
        for synset, kind in edges:
            if kind == "exact":
                exact_by_synset[synset].append(concept)
    chains = {s: cs for s, cs in exact_by_synset.items() if len(cs) > 1}
    lines.append(f"reviewed exact edges that join two or more concept sets through one synset: {len(chains)}"
                 + ("" if not chains else " (" + "; ".join(f"{s}: {', '.join(cs)}" for s, cs in list(chains.items())[:5]) + ")"))
    for list_id in concept_lists:
        members = set(list_members(conn, list_id))
        if members:
            lines.append(f"{list_id}: {len(members)} concept sets, {len(members & decided)} reviewed, "
                         f"{len(members - set(best) - decided)} without any proposal")
    return lines
