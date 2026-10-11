<!--
This README ships at the root of every SEMALINGO data release (Zenodo record, GitHub release).
Fill the {{placeholders}} for each release; the counts below are from the build of 2026-10-11
and should be replaced with the release manifest's counts.
-->

# SEMALINGO {{version}}

**Linked linguistic data for people and language models.** SEMALINGO joins concept lists,
cross-linguistic word lists, colexifications, semantic shifts, psycholinguistic norms and
lexical resources into one database. Every source keeps its own identifiers. Typed links
connect them, and each link records how it was made. Ask the database in SQL, from Python or R,
or let an AI assistant query it through the included MCP server, with sources cited in
every answer.

- Release: {{version}}, {{date}}
- DOI: {{doi}}
- Code and issue tracker: https://github.com/seodius/SEMALINGO
- Authors: {{authors}}

## What is in this release

The release comes in two parts so that the core can stay under CC BY. Use the core alone, or
add the share-alike part beside it.

**Core** (CC BY 4.0, WOLD CC BY 3.0 DE)

| Source | Version | What it adds |
| --- | --- | --- |
| Concepticon | v3.4.2 | 4,033 concept sets, the pivot between all sources; 217,027 glosses that concept lists use, in 56 languages |
| Concepticon gloss lookup tables | v3.4.0 | 51,273 glosses in 41 languages, used to match words to concept sets |
| NoRaRe (CLDF release) | v1.1 | 677,593 values from 126 studies: age of acquisition, frequency, concreteness, valence and more, for 142,527 words in 39 languages |
| Lexibank (lexibank-analysed) | v2.2.6 | 1,740,092 word forms (phonetic) for 3,205 concepts in 5,501 language varieties |
| CLICS4 | v1.0 | 51,562 colexifications between 1,730 concepts, weighted by language families |
| DatSemShift (CLDF) | v1.1rc | 7,043 attested semantic shifts between 4,185 concepts |
| WOLD | v4.2 | 1,814 meanings with borrowability, age and simplicity scores; 64,289 forms |
| Glottolog | v5.3 | 27,177 languages, dialects and families |
| Open English WordNet | 2025 | 107,519 synsets and 135,969 entries |
| CILI | a895d7e | 117,659 links from interlingual ids to WordNet 3.0 |
| SEMALINGO mappings | {{version}} | Links between sources: imported, automatic proposals, and reviewed ones ({{mappings_licence}}) |

**Share-alike part** (CC BY-SA 4.0; Wiktionary content also GFDL)

| Source | Version | What it adds |
| --- | --- | --- |
| Wiktionary via Kaikki (wiktextract) | snapshot of 2026-10-03 | 891,333 English and 71,787 Dutch entries with part of speech, gloss, IPA and morphology (affixes and compounds) |
| Word lists from Wiktionary and Wikipedia | pinned page revisions | Basic English (850), 1000 basic English words, Basic English combined (2,018), VOA Special English (1,530), commonly misspelled words |
| NSM semantic primes | pinned page revision | The 65 primes with their 73 English exponents |

**Not included.** Some sources may not be redistributed or have unclear terms: SUBTLEX-NL,
SUBTLEX-UK, childLex, BasiLex, SUMO, and the full Kuperman and Brysbaert norm lists. If you have
access, add them to your own copy (see [Rebuild or extend](#rebuild-or-extend)). NoRaRe already
carries about 2,600 words of the Kuperman and Brysbaert norms under CC BY.

## Files

| File | Contents |
| --- | --- |
| `semalingo-core-{{version}}.duckdb` | The core as one DuckDB database ({{size_core}}) |
| `semalingo-sharealike-{{version}}.duckdb` | The share-alike part ({{size_sharealike}}) |
| `parquet/core/*.parquet` | The core tables as Parquet, for pandas, R or Polars |
| `MANIFEST.json` | SEMALINGO version, every source's version and checksum, row counts |
| `DATA-LICENSES.md` | Licence and redistribution terms per source |
| `ATTRIBUTION.md` | The citation each source asks for |
| `README.md` | This file |

## Quick start

### With an AI assistant (MCP)

The MCP server lets Claude, or any other MCP client, query the database. It opens the database
read-only, and SQL run through it cannot reach files or the network.

```bash
pip install "semalingo[mcp]"

# Claude Code
claude mcp add --transport stdio --scope user semalingo -- \
  semalingo mcp --db /path/to/semalingo-core-{{version}}.duckdb
```

For Claude Desktop, add this to `claude_desktop_config.json`, with the full path to the
`semalingo` command:

```json
{
  "mcpServers": {
    "semalingo": {
      "type": "stdio",
      "command": "/full/path/to/semalingo",
      "args": ["mcp", "--db", "/path/to/semalingo-core-{{version}}.duckdb"]
    }
  }
}
```

Then ask, for example:

- "Which concepts do languages most often express with the same word as ARM?"
- "What age of acquisition do the norm studies report for EYE, per language?"
- "How does Concepticon's EYE connect to WordNet?"
- "Compare FOOD and MEAT."

The server offers nine tools:

| Tool | Answers |
| --- | --- |
| `lookup` | Concepts and words named or written like the query, in every source, and what the words mean |
| `neighbours` | Nodes linked to a node, up to four steps, by relation or link type |
| `norms` | Measured values of a concept and of its words, per language and source |
| `colexifications` | Concepts expressed by the same word (CLICS) and semantic shifts (DatSemShift) |
| `path` | The shortest connections between two nodes, with every link used |
| `compare` | Two nodes side by side |
| `words` | The words languages use for a concept, from every source |
| `sources` | The sources in the database, with version and licence |
| `sql` | A read-only SQL query on the tables |

### With SQL (DuckDB)

```bash
duckdb semalingo-core-{{version}}.duckdb
```

The glosses that concept lists use for EYE (Concepticon 1248) in Dutch:

```sql
SELECT DISTINCT f.written_form, f.source_id
FROM relations r
JOIN forms f ON f.form_id = r.from_id
WHERE r.relation_type = 'expresses'
  AND r.to_id = 'concepticon:1248'
  AND f.language = 'dutc1256';
```

Every age-of-acquisition value NoRaRe holds for EYE, per language:

```sql
SELECT f.language, f.written_form, p.property, p.value_num
FROM mappings m
JOIN relations r ON r.to_id = m.from_id AND r.relation_type = 'expresses'
JOIN forms f ON f.form_id = r.from_id
JOIN properties p ON p.node_id = f.form_id
JOIN property_types t ON t.source_id = p.source_id AND t.property = p.property
WHERE m.to_id = 'concepticon:1248'
  AND m.from_id LIKE 'norare:%'
  AND t.construct = 'aoa'
ORDER BY f.language;
```

The concept sets that most concept lists include:

```sql
SELECT c.concept_id, c.gloss, COUNT(*) AS lists
FROM relations r
JOIN concepts c ON c.concept_id = r.from_id
WHERE r.relation_type = 'in_list'
  AND r.to_id LIKE 'concepticon:list/%'
  AND c.source_id = 'concepticon'
GROUP BY c.concept_id, c.gloss
ORDER BY lists DESC
LIMIT 20;
```

### With Python

```python
import duckdb
from semalingo.ops import Graph

graph = Graph(duckdb.connect("semalingo-core-{{version}}.duckdb", read_only=True))
graph.colexifications("concepticon:1673")      # ARM: HAND in 53 families, WING, BRANCH, ...
graph.words("concepticon:256", language="nl")  # FOOD in Dutch
graph.path("concepticon:1248", "oewn:oewn-05318579-n")
```

The Parquet files work without SEMALINGO installed, for example
`pandas.read_parquet("parquet/core/mappings.parquet")`.

## How the data fits together

**Nodes.** Every concept, word and list has an id of the form `<source>:<local id>`:
`concepticon:1248` (EYE), `oewn:oewn-05318579-n` (a WordNet synset), `clics:eye`,
`lexibank:form/wold-Dutch-eye-1`. Languages are Glottocodes (`stan1293` English, `dutc1256`
Dutch).

**Tables.**

| Table | Holds |
| --- | --- |
| `sources` | Every loaded source, with version and licence |
| `languages` | Glottolog languages, dialects and families |
| `concepts` | Concept sets, meanings, synsets, lists |
| `forms` | Written or transcribed words, each with its language |
| `relations` | Typed edges inside a source: `expresses`, `in_list`, `hypernym`, `colexification`, `shift_polysemy`, ... |
| `properties` | Values on a node: norms, frequencies, definitions, categories |
| `property_types` | What each property measures, so values from different studies line up (all age-of-acquisition norms have construct `aoa`) |
| `mappings` | Links between sources, typed and with provenance |

**Links between sources.** Sources are never merged: a mapping links two nodes and says how
they relate and how the link was made.

| Field | Values |
| --- | --- |
| `mapping_type` | `exact`, `close`, `broader`, `narrower`, `related` (as in SKOS) |
| `method` | `imported` (given by the source itself), `gloss` (an automatic proposal from matching names), `llm` (proposed by a language model), `manual` (reviewed by the person named in `reviewer`) |
| `confidence` | 0 to 1 |

Concepticon is the pivot: most sources link their concepts to Concepticon concept sets, so a
question about a concept reaches every source through it.

## Quality and known limits

- **Automatic links are proposals.** For each Concepticon concept set, the right WordNet synset
  is the first proposal in about 86% of a spot check and among the first three in about 95%.
  Reviewed links have `method = 'manual'`; {{reviewed_count}} are reviewed in this release.
  Filter on `method` when it matters.
- **Coverage is uneven.** Norms are densest for English and Dutch. Concepticon covers concrete
  and basic vocabulary well and abstract vocabulary thinly: about 160 of Ogden's 850 Basic
  English words have no concept set.
- **Lexibank forms are phonetic** transcriptions, not spellings.
- **Errors in the sources stay in.** Known cases: in Łuniewska et al.'s list "watch"
  (wristwatch) is linked to WATCH (to look at), and Concepticon's Dutch lookup partly links
  "oog" to EAT.

Report problems at https://github.com/seodius/SEMALINGO/issues.

## Licences

- **Data:** every source keeps its own terms; see `DATA-LICENSES.md`. The core is CC BY 4.0
  (WOLD: CC BY 3.0 DE). The share-alike part is CC BY-SA 4.0, and Wiktionary content is also
  GFDL. Anything you derive from the share-alike part stays share-alike.
- **SEMALINGO's own mappings:** {{mappings_licence}}.
- **Code:** Apache License 2.0.

## How to cite

Cite SEMALINGO and the sources whose data you use. `ATTRIBUTION.md` lists the citation each
source asks for.

> {{authors}} ({{year}}). SEMALINGO: linked linguistic data for people and language models
> (version {{version}}) [Data set]. Zenodo. {{doi}}

## Rebuild or extend

Every release is built from pinned source versions by the code in the repository; `MANIFEST.json`
lists them with checksums.

```bash
pip install "semalingo[mcp]"
semalingo build                  # fetch and load every downloadable source
semalingo add-file subtlex-nl /path/to/SUBTLEX-NL.xlsx   # a source you downloaded yourself
semalingo load subtlex-nl
semalingo golden                 # questions with known answers, as a check
```

## Changes

See the release notes at https://github.com/seodius/SEMALINGO/releases.
