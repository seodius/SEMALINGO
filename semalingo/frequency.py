"""Helpers for word-frequency tables: reading spreadsheets and computing Zipf values."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterator


def xlsx_rows(path: Path, sheet: int = 0) -> Iterator[dict]:
    """Rows of an Excel sheet as dicts keyed by the header row (cached values, not formulas)."""
    import openpyxl

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = workbook.worksheets[sheet].iter_rows(values_only=True)
        header = [str(h).strip() if h is not None else "" for h in next(rows)]
        for values in rows:
            yield dict(zip(header, values))
    finally:
        workbook.close()


def is_word(text) -> bool:
    """Skip punctuation and number-only entries."""
    return isinstance(text, str) and any(ch.isalpha() for ch in text)


def zipf_values(counts: dict[str, float]) -> dict[str, float]:
    """Zipf = log10((count + 1) / (tokens in millions + types in millions)) + 3 (van Heuven et al. 2014).

    Computed from the table itself, so every frequency source gets the same scale.
    """
    tokens = sum(counts.values()) / 1e6
    types = len(counts) / 1e6
    denominator = tokens + types
    return {word: math.log10((count + 1) / denominator) + 3 for word, count in counts.items()}
