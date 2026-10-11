# SEMALINGO

**Semantics + linguistics.** SEMALINGO merges semantic and linguistic datasets (frequency
lists, age-of-acquisition norms, cross-linguistic word lists, colexifications, semantic
shifts, word associations, ontologies) into one graph for analysis. It is built first to
answer concrete design questions for a constructed language, then opened to researchers
and students in linguistics, ontology and AI.

**Status:** early. The registry, core schema, raw layer and twenty-five loaders work (Glottolog,
Concepticon with its gloss lookup tables, WOLD, CLICS4, DatSemShift, Open English WordNet,
NoRaRe, Lexibank, Wiktionary via Kaikki (English, Dutch), SUBTLEX-US/-NL/-UK, childLex, Kuperman AoA, Brysbaert concreteness, SUMO
with CILI, and six word lists including Basic English and the NSM primes), and so does a first mapping pass: gloss matching of
any source's words to Concepticon. Reviewed mappings, the graph and the operations follow
(see [the build steps](#build-steps)).

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

Words from any loaded source can be linked to Concepticon concept sets through Concepticon's
own gloss lookup tables (step 4, first pass). Each link is a mapping with method `gloss`, type
`close` and a confidence: the share of the gloss's uses in Concepticon's lists that go to that
concept set ("watch" splits over WATCH, WRISTWATCH, LOOK, CLOCK).

```bash
semalingo build concepticon concepticon-maps
semalingo match subtlex-uk subtlex-nl childlex oewn
```

Concepticon concept sets get WordNet proposals, which are reviewed on a review page and
kept as reviewed mappings in `mappings/` (see [mappings/README.md](mappings/README.md)):

```bash
semalingo link-wordnet
semalingo review-queue queue.json && python scripts/build_review_page.py queue.json review.html
semalingo load-mappings
semalingo check-mappings
```

Your own concept lists, made on the review page or written by hand in `data/lists/`, join the
review queue and the core tables (source `custom`). A list can hold existing concept sets and new
concepts with a gloss, a definition and the concept set they are closest to:

```bash
semalingo export-lists review-export/ --reviewer <name>   # the page's lists -> data/lists/*.tsv
semalingo load-lists && semalingo link-wordnet            # lists and new concepts into the tables
semalingo review-queue queue.json                          # the queue now includes your lists
```

For every concept set and candidate synset the page shows where it sits (`semalingo.context`):
the full SUMO path up to Entity with SUMO's documentation, ground facts and the classes its
rules name together with the term; the WordNet hypernym path and the synset's part, member,
substance, entailment, cause and similarity relations; and Concepticon's own relations between
concept sets (has part, part of, broader, narrower, ...).

The review page also shows how languages express each concept set (`semalingo.usage`): the
words concept lists use for it in 56 languages (Concepticon, with SUBTLEX Zipf frequencies),
Lexibank's forms, forms that stand for several concept sets in one word list, how many
families have a word for it, and its most common colexifications (CLICS). It reads whatever
of `glottolog`, `concepticon`, `lexibank`, `clics` and the frequency lists is loaded.

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
  languages.py        language codes (forms carry Glottocodes)
  matching.py         gloss matching: words of any source -> Concepticon concept sets
  wikitext.py         reading word lists out of Wiktionary/Wikipedia wikitext
  linking.py          WordNet proposals for Concepticon concept sets (step 4)
  review.py           review queue, reviewed mappings and mapping checks (step 4)
  loaders/            one loader per source: glottolog, concepticon, wold, clics, datsemshift, oewn,
                      norare, concepticon-maps, subtlex-us/-nl/-uk and childlex (frequencies.py),
                      word lists from Wiktionary/Wikipedia (wordlists.py): Basic English, NSM
                      primes, 1000 basic words, Basic English combined, VOA Special English,
                      common misspellings; SUMO and CILI (sumo.py); lexibank; Kuperman AoA
                      and Brysbaert concreteness (norms.py); Kaikki/Wiktionary morphology (kaikki.py)
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
