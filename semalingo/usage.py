"""How languages express a concept set: the words they use for it and what else those words mean.

For a set of Concepticon concept sets, `concept_usage` gathers per concept set:

- words: the written words that concept lists use for it, per language (Concepticon's glosses,
  56 languages), with a Zipf frequency where a frequency list for that language is loaded
  (SUBTLEX-NL for Dutch, SUBTLEX-UK for English, ...);
- forms: the forms Lexibank's word lists record for it in the same languages (mostly phonetic
  transcriptions from field data), with the number of word lists that record each one;
- shared: in those languages, the other concept sets that the same Lexibank form stands for in
  the same word list: a colexification inside one language (Dutch "hout" for WOOD and TREE);
- spread: in how many Lexibank varieties, languages and families it has a form at all;
- colexified: the concept sets that CLICS finds colexified with it in the most language families.

Names of languages come from the languages table (Glottolog); without Glottolog loaded the
Glottocode stands in for the name.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict

LIMIT = 4  # words, forms and shared forms kept per concept set and language
COLEXIFIED = 8  # colexified concept sets kept per concept set


def _rows(conn, sql, params=()):
    return conn.execute(sql, list(params)).fetchall()


NOTE = re.compile(r"\[[^\]]*\]")  # editors' notes in list glosses: "木头 [B = 木材]"


def _word(text: str | None) -> str:
    """A list gloss as a word: notes and the asterisks some lists mark words with are dropped."""
    return " ".join(NOTE.sub(" ", text or "").split()).strip("* ")


def _fold(word: str) -> str:
    return unicodedata.normalize("NFKD", word).encode("ascii", "ignore").decode().casefold()


def _latin(word: str) -> bool:
    return all(ord(ch) <= 0x24F for ch in word if ch.isalpha())


def _distinct(words: list[str]) -> list[str]:
    """Words without spelling variants: "árbol" and "Arbol" are one word, and a romanization
    ("Diereva") goes when the language's own script ("дерево") is there."""
    native = any(not _latin(w) for w in words)
    kept, seen = [], set()
    for word in words:
        key = _fold(word) or word.casefold()
        if key in seen or (native and _latin(word)):
            continue
        seen.add(key)
        kept.append(word)
    return kept


def _segments(text: str | None) -> str:
    """Lexibank segments as one transcription: "h ɑ n t" -> hɑnt, "_" marks a word break."""
    return "".join((text or "").split()).replace("_", " ").replace("+", "")


def gloss_languages(conn) -> list[str]:
    """Glottocodes of the languages Concepticon's concept lists are glossed in, most glossed first."""
    return [
        language
        for language, _ in _rows(
            conn,
            "SELECT language, COUNT(*) FROM forms WHERE source_id = 'concepticon' AND form_id LIKE 'concepticon:gloss/%' "
            "GROUP BY language ORDER BY COUNT(*) DESC, language",
        )
    ]


def language_names(conn, glottocodes) -> dict[str, dict]:
    wanted = set(glottocodes)
    names = {}
    for code, name, family in _rows(conn, "SELECT glottocode, name, family_name FROM languages WHERE source_id = 'glottolog'"):
        if code in wanted:
            names[code] = {"name": name or code, "family": family or ""}
    return {code: names.get(code, {"name": code, "family": ""}) for code in glottocodes}


def _zipf(conn) -> dict[tuple[str, str], float]:
    """(language, lowercased word) -> the highest Zipf value any loaded frequency list gives it."""
    found: dict[tuple[str, str], float] = {}
    for language, word, value in _rows(
        conn,
        "SELECT f.language, f.written_form, p.value_num FROM properties p JOIN forms f ON f.form_id = p.node_id "
        "WHERE p.property = 'zipf' AND p.value_num IS NOT NULL",
    ):
        key = (language, word.casefold())
        if value > found.get(key, -1.0):
            found[key] = value
    return found


def concept_usage(conn, concepts, languages=None) -> dict:
    """Words, forms, colexifications and spread per concept set; see the module docstring.

    Returns {"languages": {glottocode: {name, family}}, "concepts": {concept node: {...}}}.
    """
    concepts = list(concepts)
    targets = set(concepts)
    languages = list(languages or gloss_languages(conn))
    chosen = set(languages)
    gloss_of = dict(_rows(conn, "SELECT concept_id, gloss FROM concepts WHERE source_id = 'concepticon'"))
    usage = {c: {"words": {}, "forms": {}, "shared": {}, "spread": {}, "colexified": []} for c in concepts}

    # Concept lists' own words, per language
    zipf = _zipf(conn)
    words: dict[tuple[str, str], Counter] = defaultdict(Counter)
    spelled: dict[tuple[str, str, str], str] = {}
    for concept, language, text in _rows(
        conn,
        "SELECT r.to_id, f.language, f.written_form FROM forms f "
        "JOIN relations r ON r.from_id = f.form_id AND r.relation_type = 'expresses' AND r.source_id = 'concepticon' "
        "WHERE f.source_id = 'concepticon' AND f.form_id LIKE 'concepticon:gloss/%'",
    ):
        word = _word(text)
        if concept in targets and language in chosen and word:
            words[(concept, language)][word.casefold()] += 1
            spelled.setdefault((concept, language, word.casefold()), word)
    for (concept, language), counts in words.items():
        ranked = _distinct([spelled[(concept, language, key)] for key, _ in counts.most_common()])[:LIMIT]
        usage[concept]["words"][language] = [
            {"w": word, **({"z": zipf[(language, word.casefold())]} if (language, word.casefold()) in zipf else {})}
            for word in ranked
        ]

    # Lexibank: which Lexibank concepts stand for which concept sets
    lexibank_concept = {
        source: target
        for source, target in _rows(
            conn,
            "SELECT from_id, to_id FROM mappings WHERE from_id LIKE 'lexibank:%' AND to_id LIKE 'concepticon:%' AND method = 'imported'",
        )
    }
    family = {code: fam or code for code, fam in _rows(conn, "SELECT glottocode, family_id FROM languages WHERE source_id = 'glottolog'")}

    spread: dict[str, list[set]] = defaultdict(lambda: [set(), set(), set()])
    forms: dict[tuple[str, str], Counter] = defaultdict(Counter)
    by_variety_form: dict[tuple[str, str], set] = defaultdict(set)  # (variety, form) -> concept sets
    language_of_variety: dict[str, str] = {}
    for form_id, language, written, lexibank, variety, segments in _rows(
        conn,
        "SELECT f.form_id, f.language, f.written_form, e.to_id, v.to_id, p.value_text FROM forms f "
        "JOIN relations e ON e.from_id = f.form_id AND e.relation_type = 'expresses' AND e.source_id = 'lexibank' "
        "JOIN relations v ON v.from_id = f.form_id AND v.relation_type = 'in_list' AND v.source_id = 'lexibank' "
        "LEFT JOIN properties p ON p.node_id = f.form_id AND p.source_id = 'lexibank' AND p.property = 'segments' "
        "WHERE f.source_id = 'lexibank'",
    ):
        concept = lexibank_concept.get(lexibank)
        if concept is None:
            continue
        if concept in targets:
            counts = spread[concept]
            counts[0].add(variety)
            counts[1].add(language)
            counts[2].add(family.get(language, language))
        if language in chosen:
            form = _segments(segments) or written.replace(".", "")
            language_of_variety[variety] = language
            by_variety_form[(variety, form)].add(concept)
            if concept in targets:
                forms[(concept, language)][form] += 1
    for concept, (varieties, langs, families) in spread.items():
        usage[concept]["spread"] = {"varieties": len(varieties), "languages": len(langs), "families": len(families)}
    for (concept, language), counts in forms.items():
        usage[concept]["forms"][language] = [{"f": form, "n": n} for form, n in counts.most_common(LIMIT)]

    # One form, several concept sets, in one word list
    shared: dict[tuple[str, str], dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for (variety, form), meanings in by_variety_form.items():
        if len(meanings) < 2:
            continue
        language = language_of_variety[variety]
        for concept in meanings & targets:
            for other in meanings - {concept}:
                shared[(concept, language)][form].add(other)
    for (concept, language), by_form in shared.items():
        ranked = sorted(by_form.items(), key=lambda item: (-len(item[1]), item[0]))[:LIMIT]
        usage[concept]["shared"][language] = [
            {"f": form, "also": sorted(gloss_of.get(o, o) for o in others)} for form, others in ranked
        ]

    # CLICS: colexifications across languages, by number of families
    clics_concept = {
        source: target
        for source, target in _rows(
            conn, "SELECT from_id, to_id FROM mappings WHERE from_id LIKE 'clics:%' AND to_id LIKE 'concepticon:%' AND method = 'imported'"
        )
    }
    colexified: dict[str, Counter] = defaultdict(Counter)
    for a, b, families in _rows(
        conn, "SELECT from_id, to_id, weight FROM relations WHERE source_id = 'clics' AND relation_type = 'colexification'"
    ):
        a, b = clics_concept.get(a), clics_concept.get(b)
        if not a or not b or a == b:
            continue
        for x, y in ((a, b), (b, a)):
            if x in targets:
                colexified[x][y] = max(colexified[x][y], int(families or 0))
    for concept, counts in colexified.items():
        usage[concept]["colexified"] = [
            {"c": other, "g": gloss_of.get(other, other), "fam": n} for other, n in counts.most_common(COLEXIFIED) if n > 0
        ]

    return {"languages": language_names(conn, languages), "concepts": usage}
