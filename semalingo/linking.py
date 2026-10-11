"""Link Concepticon concept sets (and new concepts from custom lists) to Open English WordNet synsets (step 4, pass 1).

For every concept set this proposes up to a few synsets, each as a mapping with method
"gloss", type "close" and a confidence. Evidence, per candidate synset:

- lexical: the concept's English labels (its own gloss, the English words the concept lists
  use for it, Concepticon's lookup) that are lemmas of the synset, weighted by how often the
  lists use each label and by the synset's sense number for that lemma (sense 1 is the most
  frequent);
- part of speech: the concept's ontological category (Person/Thing, Action/Process,
  Property, ...) should agree with the synset's part of speech;
- definition: word overlap between the Concepticon definition and the synset definition.

Proposals are for review, not facts: an approved one becomes a "manual" mapping with a
reviewer (see semalingo.review).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .languages import ENGLISH
from .matching import gloss_keys
from .writer import COLUMNS, bulk_insert, dedupe, is_duckdb

# How well a synset's part of speech fits a concept's ontological category (missing = 0.1).
POS_FIT = {
    "Person/Thing": {"n": 1.0},
    "Action/Process": {"v": 1.0},
    "Property": {"a": 1.0, "s": 1.0, "r": 0.6},
    "Number": {"n": 1.0, "a": 1.0, "s": 1.0},
    "Classifier": {"n": 1.0},
}
DEFINITION_BASE = 0.1  # how much a candidate scores with no definition overlap at all
WORD = re.compile(r"[a-z]+")
STOPWORDS = set(
    "a an the of to in on at by for with from as or and but not no is are be been being was were it its this that "
    "these those which who whom whose what when where how than then so such into out up down over under about any "
    "some all each every other another one ones something someone used use using usually especially often very more "
    "most less least can may might will would should could has have had do does did done etc e g i".split()
)


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def content_words(text: str | None) -> list[str]:
    return [stem(w) for w in WORD.findall((text or "").lower()) if w not in STOPWORDS and len(w) > 2]


def concepticon_gloss_labels(gloss: str) -> list[str]:
    """English labels in a Concepticon gloss: "RAINING OR RAIN" -> raining, rain; "TEAR (OF EYE)" -> tear."""
    labels = []
    for part in re.split(r"\s+OR\s+", gloss or ""):
        labels += gloss_keys(part, ENGLISH)
    return labels


def spellings(label: str) -> list[str]:
    """A label and its closed and hyphenated spellings: "door knocker" -> doorknocker, door-knocker."""
    if " " not in label:
        return [label]
    return [label, label.replace(" ", ""), label.replace(" ", "-")]


def qualifier(gloss: str) -> str:
    """The bracketed part of a Concepticon gloss, which says which sense is meant: "WALK (MANNER)" -> manner."""
    return " ".join(re.findall(r"\(([^)]*)\)", gloss or ""))


@dataclass
class Concept:
    node: str
    gloss: str
    definition: str = ""
    category: str = ""
    labels: Counter = field(default_factory=Counter)


@dataclass
class Synset:
    node: str
    pos: str
    definition: str
    lemmas: set = field(default_factory=set)
    hypernyms: list = field(default_factory=list)

    def document(self, synsets: dict[str, "Synset"]) -> str:
        """What a synset is: its definition, its lemmas, and the lemmas of its hypernyms (a spade is a shovel)."""
        broader = " ".join(" ".join(synsets[h].lemmas) for h in self.hypernyms if h in synsets)
        return f"{self.definition} {' '.join(self.lemmas)} {broader}"


def read_concepts(conn) -> dict[str, Concept]:
    concepts = {
        node: Concept(node, gloss or "")
        for node, gloss in conn.execute(
            "SELECT concept_id, gloss FROM concepts WHERE source_id = 'concepticon' AND kind = 'concept'"
        ).fetchall()
    }
    for node, prop, value in conn.execute(
        "SELECT node_id, property, value_text FROM properties WHERE source_id = 'concepticon' "
        "AND property IN ('definition', 'ontological_category')"
    ).fetchall():
        if node in concepts:
            if prop == "definition":
                concepts[node].definition = value or ""
            else:
                concepts[node].category = value or ""
    concepts.update(read_custom_concepts(conn))
    for concept in concepts.values():
        for label in concepticon_gloss_labels(concept.gloss):
            concept.labels[label] += 3  # the concept's own name counts as several list uses
    # English words that the concept lists use for each concept set
    for concept_node, text in conn.execute(
        "SELECT r.to_id, f.written_form FROM forms f JOIN relations r ON r.from_id = f.form_id AND r.relation_type = 'expresses' "
        "WHERE f.source_id = 'concepticon' AND f.language = ?", [ENGLISH]
    ).fetchall():
        if concept_node in concepts:
            for label in gloss_keys(text, ENGLISH):
                concepts[concept_node].labels[label] += 1
    # A new concept also borrows the labels of the concept set it is closest to, together worth
    # one use: "SEE ON PURPOSE" (closest: SEE) can then find "see" in WordNet
    for node, closest in conn.execute(
        "SELECT from_id, to_id FROM mappings WHERE method = 'imported' AND from_id LIKE 'custom:%' AND to_id LIKE 'concepticon:%'"
    ).fetchall():
        if node in concepts and closest in concepts:
            borrowed = dict(concepts[closest].labels)
            total = sum(borrowed.values()) or 1
            for label, uses in borrowed.items():
                concepts[node].labels[label] += uses / total
    return concepts


def read_custom_concepts(conn) -> dict[str, Concept]:
    """New concepts from custom lists (semalingo.lists): their gloss, definition and category."""
    concepts = {
        node: Concept(node, gloss or "")
        for node, gloss in conn.execute(
            "SELECT concept_id, gloss FROM concepts WHERE source_id = 'custom' AND kind = 'concept'"
        ).fetchall()
    }
    for node, prop, value in conn.execute(
        "SELECT node_id, property, value_text FROM properties WHERE source_id = 'custom' "
        "AND property IN ('definition', 'ontological_category')"
    ).fetchall():
        if node in concepts:
            setattr(concepts[node], "definition" if prop == "definition" else "category", value or "")
    return concepts


def read_wordnet(conn) -> tuple[dict[str, Synset], dict[str, list[tuple[str, float]]]]:
    synsets = {node: Synset(node, "", "") for (node,) in conn.execute("SELECT concept_id FROM concepts WHERE source_id = 'oewn'").fetchall()}
    for node, prop, value in conn.execute(
        "SELECT node_id, property, value_text FROM properties WHERE source_id = 'oewn' AND property IN ('pos', 'definition') "
        "AND node_id NOT LIKE 'oewn:entry/%'"
    ).fetchall():
        if node in synsets:
            setattr(synsets[node], "pos" if prop == "pos" else "definition", value or "")
    for child, parent in conn.execute(
        "SELECT from_id, to_id FROM relations WHERE source_id = 'oewn' AND relation_type IN ('hypernym', 'instance_hypernym', 'similar')"
    ).fetchall():
        if child in synsets:
            synsets[child].hypernyms.append(parent)
    senses: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for lemma, synset, rank in conn.execute(
        "SELECT f.written_form, r.to_id, r.weight FROM forms f JOIN relations r ON r.from_id = f.form_id AND r.relation_type = 'sense_of' "
        "WHERE f.source_id = 'oewn'"
    ).fetchall():
        key = " ".join(lemma.casefold().split())
        senses[key].append((synset, rank or 1.0))
        if synset in synsets:
            synsets[synset].lemmas.add(key)
    return synsets, senses


def idf_table(synsets: dict[str, Synset], concepts: dict[str, Concept]) -> dict[str, float]:
    counts: Counter = Counter()
    documents = [s.definition for s in synsets.values()] + [c.definition for c in concepts.values()]
    for text in documents:
        counts.update(set(content_words(text)))
    total = len(documents)
    return {w: math.log((1 + total) / (1 + n)) for w, n in counts.items()}


def similarity(a: list[str], b: list[str], idf: dict[str, float]) -> float:
    """Cosine of IDF-weighted bags of words."""
    if not a or not b:
        return 0.0
    va, vb = Counter(a), Counter(b)
    dot = sum(va[w] * vb[w] * idf.get(w, 1.0) ** 2 for w in va.keys() & vb.keys())
    norm = math.sqrt(sum((n * idf.get(w, 1.0)) ** 2 for w, n in va.items())) * math.sqrt(
        sum((n * idf.get(w, 1.0)) ** 2 for w, n in vb.items())
    )
    return dot / norm if norm else 0.0


@dataclass
class Candidate:
    synset: str
    score: float
    lexical: float
    definition: float
    pos_ok: bool


def candidates(concept: Concept, synsets, senses, idf, top: int = 5) -> list[Candidate]:
    total = sum(concept.labels.values()) or 1
    lexical: dict[str, float] = defaultdict(float)
    best_rank: dict[str, float] = {}
    for label, uses in concept.labels.items():
        for spelling in spellings(label):
            for synset, rank in senses.get(spelling, []):
                lexical[synset] += (uses / total) / math.sqrt(rank)
                best_rank[synset] = min(best_rank.get(synset, rank), rank)
    fit = POS_FIT.get(concept.category)
    # the bracketed qualifier names the intended sense, so its words count double; the concept's
    # own name is left out, because every candidate shares it
    shared = {stem(w) for label in concepticon_gloss_labels(concept.gloss) for w in WORD.findall(label)}
    words = [w for w in content_words(f"{concept.definition} {concept.gloss} {qualifier(concept.gloss)}") if w not in shared]
    found = []
    for node, lex in lexical.items():
        synset = synsets.get(node)
        if synset is None:
            continue
        pos_fit = 1.0 if fit is None else fit.get(synset.pos, 0.1)
        definition = similarity(words, [w for w in content_words(synset.document(synsets)) if w not in shared], idf)
        if definition == 0 and (fit is None or pos_fit < 1.0):
            continue  # nothing but a shared spelling: "he" is not helium
        score = lex * pos_fit * (DEFINITION_BASE + definition)
        found.append(Candidate(node, score, lex, definition, pos_fit == 1.0))
    found.sort(key=lambda c: -c.score)
    return found[:top]


def link(conn, top: int = 3) -> dict[str, int]:
    """Write Concepticon -> OEWN proposals as gloss mappings; return counts."""
    concepts = read_concepts(conn)
    synsets, senses = read_wordnet(conn)
    idf = idf_table(synsets, concepts)
    rows = []
    linked = 0
    for concept in concepts.values():
        found = candidates(concept, synsets, senses, idf, top)
        if not found:
            continue
        linked += 1
        total = sum(c.score for c in found)
        for c in found:
            rows.append((concept.node, c.synset, "close", round(c.score / total, 4), "gloss", None))
    conn.execute(
        "DELETE FROM mappings WHERE method = 'gloss' AND (from_id LIKE 'concepticon:%' OR from_id LIKE 'custom:%') AND to_id LIKE 'oewn:%'"
    )
    bulk_insert(conn, "mappings", COLUMNS["mappings"], dedupe("mappings", rows))
    if not is_duckdb(conn):
        conn.commit()
    return {"concepts": len(concepts), "linked": linked, "mappings": len(rows)}
