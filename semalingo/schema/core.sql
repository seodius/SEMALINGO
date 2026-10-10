-- SEMALINGO core tables: the source of truth. The graph is generated from these, never edited by hand.
-- Portable SQL: it targets DuckDB and also runs on SQLite, which the tests use as a smoke check.
-- Node ids are "<source id>:<local id>", e.g. "concepticon:1209" (see semalingo/ids.py).

CREATE TABLE IF NOT EXISTS sources (
    source_id    TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    version      TEXT,
    licence      TEXT,
    loaded_at    TIMESTAMP
);

-- A written word in a language, as one source lists it.
CREATE TABLE IF NOT EXISTS forms (
    form_id      TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    language     TEXT NOT NULL,              -- Glottocode or ISO 639-3
    written_form TEXT NOT NULL
);

-- A concept, meaning, sense (e.g. a WordNet synset), ontology class, semantic prime or concept list,
-- as one source defines it.
CREATE TABLE IF NOT EXISTS concepts (
    concept_id   TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('concept', 'meaning', 'sense', 'class', 'prime', 'list')),
    gloss        TEXT
);

-- Edges inside one source: hypernym, part_of, colexification, shift, association, derivation, ...
CREATE TABLE IF NOT EXISTS relations (
    source_id     TEXT NOT NULL,
    from_id       TEXT NOT NULL,
    to_id         TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    weight        DOUBLE,
    PRIMARY KEY (source_id, from_id, to_id, relation_type)
);

-- Norms on a node: frequency, aoa_rated, aoa_test_grade, concreteness, borrowability, ...
CREATE TABLE IF NOT EXISTS properties (
    node_id      TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    property     TEXT NOT NULL,
    value_num    DOUBLE,
    value_text   TEXT,
    PRIMARY KEY (node_id, source_id, property),
    CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);

-- Links between sources (SKOS-style). Nodes are linked, never merged.
-- Every edge records how it was made; a manual edge must name its reviewer.
CREATE TABLE IF NOT EXISTS mappings (
    from_id      TEXT NOT NULL,
    to_id        TEXT NOT NULL,
    mapping_type TEXT NOT NULL CHECK (mapping_type IN ('exact', 'close', 'broader', 'narrower', 'related')),
    confidence   DOUBLE NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    method       TEXT NOT NULL CHECK (method IN ('imported', 'gloss', 'llm', 'manual')),
    reviewer     TEXT,
    reviewed_at  TIMESTAMP,
    PRIMARY KEY (from_id, to_id, mapping_type, method),
    CHECK (method <> 'manual' OR reviewer IS NOT NULL)
);
