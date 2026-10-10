# Data

Local working data. Nothing in here except this file is committed.

- `raw/<source id>/<version>/` holds downloads exactly as fetched, with a `SHA256SUMS` manifest.
- `staging/` holds intermediate files from the loaders.
- The DuckDB database (`*.duckdb`) is built from these and can always be rebuilt.
