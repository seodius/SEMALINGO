# Mappings

Mapping edges link nodes from different sources. Nodes are never merged: a Concepticon
concept and a WordNet sense stay two nodes, joined by a typed edge that says how sure we
are and who decided.

Reviewed mappings live here as versioned, tab-separated files, one file per pair of
sources (for example `concepticon__oewn.tsv`), so every change shows up in review. A
companion file `<pair>.unmatched.tsv` lists the concepts a reviewer found no equivalent for
(pronouns and function words usually have no WordNet synset): they are flagged as unmapped
on purpose, not forgotten.

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

## How Concepticon–WordNet links are made

1. `semalingo link-wordnet` proposes up to three Open English WordNet synsets for every
   Concepticon concept set (method `gloss`, type `close`). Evidence: the concept's English
   labels that are lemmas of the synset (weighted by how often concept lists use each label and
   by WordNet's sense order), the fit between Concepticon's ontological category and the
   synset's part of speech, and word overlap between the two definitions (the synset's
   hypernyms included; a spade is a shovel).
2. `semalingo review-queue queue.json` writes the proposals for a priority batch (by default
   the NSM primes, Swadesh 100 and 200, Leipzig–Jakarta, Ogden's Basic English parts,
   Łuniewska's early words, every concept set that at least 50 Concepticon lists use
   (`widely-used:50`), and Ogden's 850 Basic English words, each matched to the concept set
   its gloss match and its Basic English category suit best (`basic-english:words`): about
   1,100 concept sets) and `scripts/build_review_page.py` turns it into
   the review page. Each decision there is stored with its reviewer. Beside the proposals the
   page shows the concept set's words and forms in other languages and what CLICS finds it
   colexified with, which often settles which sense is meant (Dutch "groot" is both BIG and
   TALL; TREE and WOOD share a word in 58 families).
   Your own lists (made on the page or in `data/lists/`) can add concept sets and new concepts
   to the queue: `semalingo export-lists`, `semalingo load-lists`, then link and build the queue
   again. Decisions on new concepts go to `data/lists/custom__oewn.tsv`, not to this folder.
3. `semalingo export-review <folder> --reviewer <name>` writes the decisions to
   `concepticon__oewn.tsv` and `concepticon__oewn.unmatched.tsv`; `semalingo load-mappings`
   loads them as `manual` mappings; `semalingo check-mappings` reports coverage, unclear
   proposals, crowded synsets and chains of `exact` edges.

A spot check of 45 random concept sets found the right synset first for about 86% of
them and among the top three for about 95%. NoRaRe's own automatic Concepticon–WordNet
mapping (Bond-2013-OMW) agrees with the first proposal for 55% of its 1,406 concept sets;
many of the disagreements are errors in that mapping (BULL as a policeman, HOOK as a verb).
