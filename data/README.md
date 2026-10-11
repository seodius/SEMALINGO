# Data

Local working data. Nothing in here except this file is committed.

- `raw/<source id>/<version>/` holds downloads exactly as fetched, with a `SHA256SUMS` manifest.
- `staging/` holds intermediate files from the loaders.
- The DuckDB database (`*.duckdb`) is built from these and can always be rebuilt.
- `lists/` holds your own concept lists (`index.tsv` plus one `<list id>.tsv` per list, see
  `semalingo/lists.py`), and `custom__oewn.tsv` with the WordNet decisions on new concepts
  from those lists. They stay out of version control, so private lists stay private.
