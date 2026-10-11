"""Where a concept or a synset sits: its SUMO and WordNet hierarchies and its other relations.

For the review page (and anyone who wants more than the endpoint of a mapping):

- `sumo_context`: for SUMO terms, their parents (subclass, instance, subAttribute, subrelation;
  the parent on the longest path to the root first), documentation, ground facts in both
  directions ((disjoint Plant Animal), (typicalPart Feather Bird), decompositions, ...) and the
  classes SUMO's rules name together with them. Every ancestor is included, with its parents
  and documentation, so a reader can walk each path up to Entity.
- `wordnet_context`: for OEWN synsets, their hypernyms (and every ancestor's, with a label), and
  their other synset relations (part, member and substance holonyms and meronyms, entailment,
  causes, attribute, similar, topic), plus the antonyms of their words.
- `concept_relations`: Concepticon's own relations between concept sets (broader, narrower, part
  of, has part, ...).
"""

from __future__ import annotations

from collections import defaultdict

SUMO_PARENTS = ("subclass_of", "instance_of", "subattribute_of", "subrelation_of")
WORDNET_PARENTS = ("hypernym", "instance_hypernym")
WORDNET_RELATIONS = {
    "holo_part": "part of", "mero_part": "has part", "holo_member": "member of", "mero_member": "has member",
    "holo_substance": "substance of", "mero_substance": "made of", "entails": "entails", "causes": "causes",
    "attribute": "attribute", "similar": "similar to", "domain_topic": "topic",
}
# Concepticon's relations, read from the first concept set to the second, said of the second:
# EYE partof EYELASH (an eyelash is part of an eye) -> "has part: EYELASH"; HAIR haspart HEAD ->
# "part of: HEAD"; CAR instanceof TRUCK -> "includes: TRUCK"; BUG isa INSECT -> "is a: INSECT".
CONCEPT_RELATIONS = {
    "broader": "broader", "narrower": "narrower", "partof": "has part", "haspart": "part of", "isa": "is a",
    "instanceof": "includes", "antonymof": "opposite", "similar": "similar", "requires": "requires",
    "resultsin": "results in", "producedby": "produced by", "hasform": "has form", "transitiveof": "transitive of",
    "intransitiveof": "intransitive of",
}
DOC_LENGTH = 220


def _rows(conn, sql, params=()):
    return conn.execute(sql, list(params)).fetchall()


def _short(text: str, length: int = DOC_LENGTH) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= length else text[: length - 1].rsplit(" ", 1)[0] + "…"


def _ancestors(start, parents: dict[str, list[str]]) -> set[str]:
    seen, todo = set(), list(start)
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        todo.extend(parents.get(node, []))
    return seen


def _by_depth(parents: dict[str, list[str]]) -> dict[str, list[str]]:
    """Each node's parents, the one on the longest path to a root first."""
    depth: dict[str, int] = {}

    def walk(node, path=()):
        if node in depth:
            return depth[node]
        if node in path:  # a cycle: stop here
            return 0
        depth[node] = 0  # provisional, guards against cycles through other paths
        value = 1 + max((walk(p, path + (node,)) for p in parents.get(node, [])), default=-1)
        depth[node] = value
        return value

    ordered = {}
    for node, ps in parents.items():
        ordered[node] = sorted(dict.fromkeys(ps), key=lambda p: (-walk(p), p))
    return ordered


def sumo_context(conn, terms, facts: int = 12, mentions: int = 10) -> dict[str, dict]:
    """{term: {"n": name, "d": documentation, "p": parents, "f": facts, "m": rule mentions}} for the
    given terms ("Eye", without the "sumo:" prefix) and all their ancestors; facts and mentions
    only for the given terms. A fact is [relation, other term, 1 when the term comes first else -1]."""
    wanted = {t for t in terms if t}
    parents: dict[str, list[str]] = defaultdict(list)
    for child, parent, kind in _rows(
        conn, "SELECT from_id, to_id, relation_type FROM relations WHERE source_id = 'sumo' AND relation_type IN "
        f"({', '.join('?' * len(SUMO_PARENTS))})", SUMO_PARENTS,
    ):
        parents[child[5:]].append(parent[5:])
    parents = _by_depth(parents)
    keep = _ancestors(wanted, parents)
    names = {node[5:]: gloss for node, gloss in _rows(conn, "SELECT concept_id, gloss FROM concepts WHERE source_id = 'sumo'")}
    docs = {node[5:]: text for node, text in _rows(
        conn, "SELECT node_id, value_text FROM properties WHERE source_id = 'sumo' AND property = 'documentation'")}
    out = {}
    for term in keep:
        entry = {"p": parents.get(term, [])}
        if names.get(term) and names[term] != term:
            entry["n"] = names[term]
        if docs.get(term):
            entry["d"] = _short(docs[term])
        out[term] = entry
    found: dict[str, list] = defaultdict(list)
    seen_mentions: dict[str, list] = defaultdict(list)
    for a, b, kind, weight in _rows(
        conn, "SELECT from_id, to_id, relation_type, weight FROM relations WHERE source_id = 'sumo' AND relation_type NOT IN "
        f"({', '.join('?' * len(SUMO_PARENTS))})", SUMO_PARENTS,
    ):
        a, b = a[5:], b[5:]
        if kind == "rule_mentions":
            if a in wanted:
                seen_mentions[a].append((weight or 0, b))
            continue
        if a in wanted:
            found[a].append([kind, b, 1])
        if b in wanted:
            found[b].append([kind, a, -1])
    for term in wanted & set(out):
        if found.get(term):
            out[term]["f"] = sorted(found[term], key=lambda f: (f[0], f[2], f[1]))[:facts]
        if seen_mentions.get(term):
            top = sorted(seen_mentions[term], key=lambda m: (-m[0], m[1]))[:mentions]
            out[term]["m"] = [[other, int(n)] for n, other in top]
    return out


def wordnet_context(conn, synsets, relations: int = 12) -> dict[str, dict]:
    """{synset: {"l": label, "p": hypernyms, "r": [[relation, label], ...]}} for the given OEWN
    synsets and their ancestors; relations only for the given synsets."""
    wanted = set(synsets)
    parents: dict[str, list[str]] = defaultdict(list)
    for child, parent in _rows(
        conn, "SELECT from_id, to_id FROM relations WHERE source_id = 'oewn' AND relation_type IN (?, ?)", WORDNET_PARENTS,
    ):
        parents[child].append(parent)
    keep = _ancestors(wanted, parents)
    lemmas: dict[str, list[str]] = defaultdict(list)
    entries: dict[str, list[str]] = defaultdict(list)
    for entry, word, synset in _rows(
        conn, "SELECT f.form_id, f.written_form, r.to_id FROM forms f JOIN relations r ON r.from_id = f.form_id "
        "AND r.relation_type = 'sense_of' WHERE f.source_id = 'oewn' ORDER BY r.weight",
    ):
        lemmas[synset].append(word)
        if synset in wanted:
            entries[synset].append(entry)

    def label(synset: str) -> str:
        words = list(dict.fromkeys(lemmas.get(synset, [])))
        return ", ".join(words[:2]) or synset.split(":", 1)[1]

    out = {s: {"l": label(s), "p": parents.get(s, [])} for s in keep}
    found: dict[str, list] = defaultdict(list)
    for a, b, kind in _rows(
        conn, "SELECT from_id, to_id, relation_type FROM relations WHERE source_id = 'oewn' AND relation_type IN "
        f"({', '.join('?' * len(WORDNET_RELATIONS))})", list(WORDNET_RELATIONS),
    ):
        if a in wanted:
            found[a].append([WORDNET_RELATIONS[kind], label(b)])
    # antonyms are recorded between words (entries), not synsets
    by_entry = {e: s for s, es in entries.items() for e in es}
    for a, b in _rows(conn, "SELECT from_id, to_id FROM relations WHERE source_id = 'oewn' AND relation_type = 'antonym'"):
        if a in by_entry:
            word = b.split("oewn-", 1)[-1].rsplit("-", 1)[0].replace("_", " ")
            found[by_entry[a]].append(["opposite (of a word)", word])
    for synset, rels in found.items():
        out[synset]["r"] = [list(r) for r in dict.fromkeys(tuple(r) for r in rels)][:relations]
    return out


def concept_relations(conn, concepts) -> dict[str, list[list[str]]]:
    """{concept: [[what the other is, other concept, its gloss], ...]} from Concepticon's concept
    relations, e.g. ["has part", "concepticon:17", "EYELID"] for EYE."""
    wanted = set(concepts)
    order = list(CONCEPT_RELATIONS)
    gloss = dict(_rows(conn, "SELECT concept_id, gloss FROM concepts WHERE source_id IN ('concepticon', 'custom')"))
    out: dict[str, list] = defaultdict(list)
    for a, b, kind in _rows(
        conn, "SELECT from_id, to_id, relation_type FROM relations WHERE source_id = 'concepticon' AND relation_type IN "
        f"({', '.join('?' * len(order))})", order,
    ):
        if a in wanted and a != b:
            out[a].append((order.index(kind), CONCEPT_RELATIONS[kind], b, gloss.get(b, b)))
    return {c: [list(r[1:]) for r in sorted(set(rels), key=lambda r: (r[0], r[3]))] for c, rels in out.items()}
