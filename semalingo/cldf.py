"""A small CLDF reader using only the standard library.

CLDF datasets are CSV tables described by a JSON metadata file (CSVW). This reader
finds tables by CLDF component (e.g. "ParameterTable") or by file name, splits
multi-value columns on their declared separator, and reads tables that were stored
zipped ("forms.csv.zip"), as many Lexibank datasets do.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Iterator

csv.field_size_limit(2**31 - 1)


class Table:
    def __init__(self, folder: Path, spec: dict):
        self.folder = folder
        self.url: str = spec["url"]
        self.component: str = (spec.get("dc:conformsTo") or "").rsplit("#", 1)[-1]
        columns = spec.get("tableSchema", {}).get("columns", [])
        self.columns = [c["name"] for c in columns]
        self.separators = {c["name"]: c["separator"] for c in columns if c.get("separator")}

    def _open(self) -> io.TextIOBase:
        path = self.folder / self.url
        if path.exists():
            return open(path, encoding="utf-8", newline="")
        zipped = self.folder / (self.url + ".zip")
        if zipped.exists():
            archive = zipfile.ZipFile(zipped)
            member = next(n for n in archive.namelist() if Path(n).name == Path(self.url).name)
            return io.TextIOWrapper(archive.open(member), encoding="utf-8", newline="")
        raise FileNotFoundError(f"table {self.url} not found in {self.folder}")

    def __iter__(self) -> Iterator[dict]:
        with self._open() as handle:
            for row in csv.DictReader(handle):
                yield {key: self._value(key, value) for key, value in row.items() if key is not None}

    def _value(self, key: str, value: str | None):
        if value is None or value == "":
            return [] if key in self.separators else None
        if key in self.separators:
            return [part.strip() for part in value.split(self.separators[key]) if part.strip()]
        return value


class Dataset:
    def __init__(self, metadata_path: str | Path):
        self.metadata_path = Path(metadata_path)
        self.folder = self.metadata_path.parent
        with open(self.metadata_path, encoding="utf-8") as handle:
            self.metadata = json.load(handle)
        self.tables = [Table(self.folder, spec) for spec in self.metadata.get("tables", [])]

    def table(self, name: str) -> Table:
        """A table by CLDF component ("ParameterTable") or by file name ("concepts.csv")."""
        for table in self.tables:
            if table.component == name or table.url == name:
                return table
        raise KeyError(f"no table {name!r} in {self.metadata_path}")

    def has_table(self, name: str) -> bool:
        return any(t.component == name or t.url == name for t in self.tables)


def table_urls(metadata: dict) -> list[str]:
    return [spec["url"] for spec in metadata.get("tables", [])]


def to_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
