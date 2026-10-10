# Mappings

Mapping edges link nodes from different sources. Nodes are never merged: a Concepticon
concept and a WordNet sense stay two nodes, joined by a typed edge that says how sure we
are and who decided.

Reviewed mappings live here as versioned, tab-separated files, one file per pair of
sources (for example `concepticon__oewn.tsv`), so every change shows up in review.

## Columns

| Column | Meaning |
| --- | --- |
| `from_id` | node id, `<source id>:<local id>` |
| `to_id` | node id, `<source id>:<local id>` |
| `mapping_type` | `exact`, `close`, `broader`, `narrower` or `related` (SKOS-style) |
| `confidence` | 0 to 1 |
| `method` | `imported` (from the source itself), `gloss` (gloss matching), `llm` (LLM proposal) or `manual` |
| `reviewer` | who approved it; required when `method` is `manual` |
| `reviewed_at` | ISO date of the review |
| `note` | optional free text |

## Why there is no "same as"

Identity is transitive: if A = B and B = C, then A = C. A few sloppy identity links
chain river banks into money banks across the whole graph. `exact` is a mapping
between two nodes, not a merge, and the quality checks look for suspicious chains of
`exact` edges.
