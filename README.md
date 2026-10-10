# SEMALINGO

**Semantics + linguistics.** SEMALINGO merges semantic and linguistic datasets (frequency
lists, age-of-acquisition norms, cross-linguistic word lists, colexifications, semantic
shifts, word associations, ontologies) into one graph for analysis. It is built first to
answer concrete design questions for a constructed language, then opened to researchers
and students in linguistics, ontology and AI.

**Status:** early. The registry, core schema, raw layer and eleven loaders work (Glottolog,
Concepticon, WOLD, CLICS4, DatSemShift, Open English WordNet, NoRaRe, SUBTLEX-US/-NL/-UK,
childLex); mappings beyond the sources' own Concepticon links, the graph and the operations
follow (see [the build steps](#build-steps)).

## Principles

- **Link nodes, never merge them.** Each source keeps its own ids. A separate layer of
  typed mapping edges (exact, close, broader, narrower, related) connects them.
- **Provenance everywhere.** Every mapping edge records method, confidence and reviewer.
  Every answer says which sources and mappings it went through.
- **Tables are the source of truth.** The graph is generated from them and rebuilt with one command.
- **Publish code, schema and mappings, not raw data.** Licences stay attached per source.
- **Questions first.** An operation is added only when a real question needs it
  ([exit questions](docs/exit-questions.md)).
- **Gaps are findings.** Where data is thin (many languages are), the tool should say so;
  those gaps point to where research is missing.

## How it fits together

```
sources.yaml ──► data/raw/<source>/<version>/ (+ SHA256SUMS)
                        │
                        ▼
              DuckDB core tables ◄──── mapping layer (gloss match, LLM proposals, manual review)
 languages · forms · concepts · relations · properties · property_types · mappings
                        │
                        ▼
          graph projection (one named graph per source + mappings)
                        │
                        ▼
   operations: lookup · neighbours · norms · colexifications · path · compare
                        │
             ┌──────────┼──────────┐
             ▼          ▼          ▼
         MCP server  CLI/notebook  web UI (later)
```

## Getting started

With Docker (data ends up in `./data`):

```bash
docker compose build
docker compose run --rm semalingo build          # fetch and load every source that has a loader
docker compose run --rm semalingo build clics    # or just one
docker compose run --rm semalingo stats          # row counts per loaded source
```

Without Docker:

```bash
pip install -e ".[dev]"
semalingo validate                  # check sources.yaml
semalingo sources --wave first      # sources, which have a loader, what is still unverified
semalingo build                     # fetch into data/raw and load into data/semalingo.duckdb
semalingo stats
pytest
```

Some sources cannot be downloaded automatically (a licence or sign-up first). Add the file
once and it is treated like any download:

```bash
semalingo add-file subtlex-nl "SUBTLEX-NL with pos and Zipf.xlsx"
semalingo add-file subtlex-uk SUBTLEX-UK_all.xlsx
semalingo add-file childlex childlex
```

`fetch` downloads only what a loader needs (selected CLDF tables at a pinned git tag, or a
pinned release file) into `data/raw/<source>/<version>/`, with `SOURCE.json` and a
`SHA256SUMS` manifest; `load` refuses raw files that no longer match their checksums.

## Repository layout

```
sources.yaml          source registry: the single source of truth for what is loaded, and under which terms
DATA-LICENSES.md      generated from sources.yaml (semalingo licences --write)
semalingo/
  registry.py         load and validate sources.yaml
  raw.py              pinned raw layer with checksum manifests
  ids.py              node ids: "<source id>:<local id>"
  schema/core.sql     the core tables (portable SQL, DuckDB is the target)
  db.py               create the core tables
  cldf.py             a small CLDF reader (standard library only)
  fetch.py            downloads into the raw layer
  writer.py           buffered, repeatable writes into the core tables
  loaders/            one loader per source: glottolog, concepticon, wold, clics, datsemshift, oewn,
                      norare, subtlex-us/-nl/-uk and childlex (frequencies.py)
  frequency.py        spreadsheet reading and Zipf values for frequency tables
  graph/              graph projection (step 5)
  ops/                the six operations, with provenance on every result (step 6)
  mcp_server/         MCP server over the operations (step 7)
  cli.py              the semalingo command
mappings/             reviewed mapping edges as versioned TSV
tests/                unit tests; tests/golden/ holds questions with known answers
docs/                 exit questions and design notes
data/                 local working data, never committed
Dockerfile            the semalingo command in a container; compose.yaml mounts ./data
```

## Build steps

1. Exit questions and repo
2. Source registry: verify every entry in `sources.yaml` against the source itself
3. Loaders into the DuckDB core tables
4. Mapping layer
5. Graph projection
6. Operations library
7. Interfaces: MCP server first, then CLI/notebook, web UI last
8. Use it: run the exit questions, log what the tool cannot answer
9. Open it up: docs, releases with a DOI, contribution flow for mappings

## Licences

- **Code:** Apache License 2.0, see [LICENSE](LICENSE).
- **Data:** every source keeps its own terms; see [DATA-LICENSES.md](DATA-LICENSES.md),
  generated from `sources.yaml`. Raw data is never committed. Anything derived from a
  share-alike or non-commercial source stays under that source's terms.
- **SEMALINGO's own mappings and weights:** licence to be decided.
