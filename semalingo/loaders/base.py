"""The loader contract: fetch raw files into the pinned raw layer, then load them into the core tables."""

from __future__ import annotations

import posixpath
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from ..cldf import Dataset
from ..fetch import fetch_cldf, write_source_info
from ..ids import make_node_id
from ..raw import MANIFEST, raw_dir, verify_checksums, write_checksums
from ..registry import Source
from ..writer import Writer

LOADERS: dict[str, type["Loader"]] = {}


def register(cls: type["Loader"]) -> type["Loader"]:
    if cls.source_id in LOADERS:
        raise ValueError(f"a loader for {cls.source_id!r} is already registered")
    LOADERS[cls.source_id] = cls
    return cls


class Loader(ABC):
    source_id: ClassVar[str]
    ref: ClassVar[str]  # the pinned version: a git tag or an edition name

    def __init__(self, source: Source):
        if source.id != self.source_id:
            raise ValueError(f"{type(self).__name__} loads {self.source_id!r}, not {source.id!r}")
        self.source = source

    def node(self, local_id) -> str:
        return make_node_id(self.source_id, local_id)

    def raw_folder(self, raw_root: Path) -> Path:
        return raw_dir(raw_root, self.source_id, self.ref)

    def is_fetched(self, raw_root: Path) -> bool:
        folder = self.raw_folder(raw_root)
        return (folder / MANIFEST).exists() and not verify_checksums(folder)

    def fetch(self, raw_root: Path, force: bool = False) -> Path:
        """Download into raw_root/<source id>/<ref>/ unless an intact copy is already there."""
        folder = self.raw_folder(raw_root)
        if self.is_fetched(raw_root) and not force:
            return folder
        folder.mkdir(parents=True, exist_ok=True)
        self.download(folder)
        write_checksums(folder)
        return folder

    @abstractmethod
    def download(self, folder: Path) -> None:
        """Write the raw files and a SOURCE.json into folder."""

    def load(self, conn, raw_root: Path) -> dict[str, int]:
        """Load the fetched files into the core tables; return row counts per table."""
        folder = self.raw_folder(raw_root)
        problems = verify_checksums(folder)
        if problems:
            raise RuntimeError(f"{self.source_id}: raw files do not match SHA256SUMS ({'; '.join(problems[:3])}); fetch again")
        writer = Writer(conn, self.source, self.ref)
        self.read(folder, writer)
        return writer.finish()

    @abstractmethod
    def read(self, folder: Path, writer: Writer) -> None:
        """Turn the raw files into rows via writer."""


class CLDFLoader(Loader):
    """A loader for a CLDF dataset in a GitHub repository, pinned to a git tag."""

    repo: ClassVar[str]
    metadata_path: ClassVar[str] = "cldf/cldf-metadata.json"
    tables: ClassVar[tuple[str, ...] | None] = None  # file names to fetch; None = all

    def download(self, folder: Path) -> None:
        files = fetch_cldf(self.repo, self.ref, self.metadata_path, self.tables, folder)
        write_source_info(folder, source=self.source_id, repo=self.repo, ref=self.ref, files=files)

    def dataset(self, folder: Path) -> Dataset:
        return Dataset(folder / posixpath.basename(self.metadata_path))

    def concepticon(self, writer: Writer, node_id: str, concepticon_id) -> None:
        """Record the source's own link to a Concepticon concept set as an imported mapping."""
        if concepticon_id not in (None, "", "0"):
            writer.mapping(node_id, make_node_id("concepticon", concepticon_id))
