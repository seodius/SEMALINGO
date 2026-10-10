"""Loaders: one per source, each writing into the core tables.

Every loader follows the same contract (see `Loader`): fetch the raw files into the
pinned raw layer, then load them into the core tables. Loaders register themselves
with `@register` so the CLI can find them by source id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from ..registry import Source

LOADERS: dict[str, type["Loader"]] = {}


class Loader(ABC):
    source_id: ClassVar[str]

    def __init__(self, source: Source):
        if source.id != self.source_id:
            raise ValueError(f"{type(self).__name__} loads {self.source_id!r}, not {source.id!r}")
        self.source = source

    @abstractmethod
    def fetch(self, raw_root: Path) -> Path:
        """Download the raw files into raw_root/<source id>/<version>/, write SHA256SUMS, return that folder."""

    @abstractmethod
    def load(self, conn, raw_path: Path) -> None:
        """Write this source's rows into the core tables, with node ids prefixed by the source id."""


def register(cls: type[Loader]) -> type[Loader]:
    if cls.source_id in LOADERS:
        raise ValueError(f"a loader for {cls.source_id!r} is already registered")
    LOADERS[cls.source_id] = cls
    return cls
