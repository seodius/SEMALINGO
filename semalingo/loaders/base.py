"""The loader contract: fetch raw files into the pinned raw layer, then load them into the core tables."""

from __future__ import annotations

import posixpath
import shutil
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
        writer = Writer(conn, self.source, self.version(folder))
        self.read(folder, writer)
        return writer.finish()

    def version(self, folder: Path) -> str:
        """The version recorded in the sources table; snapshot sources report the date they hold."""
        return self.ref

    @abstractmethod
    def read(self, folder: Path, writer: Writer) -> None:
        """Turn the raw files into rows via writer."""


class CLDFLoader(Loader):
    """A loader for a CLDF dataset in a GitHub repository, pinned to a git tag."""

    repo: ClassVar[str]
    metadata_path: ClassVar[str] = "cldf/cldf-metadata.json"
    tables: ClassVar[tuple[str, ...] | None] = None  # file names to fetch; None = all

    def is_fetched(self, raw_root: Path) -> bool:
        """Also False when a loader now needs a table that an earlier fetch did not download."""
        if not super().is_fetched(raw_root):
            return False
        folder = self.raw_folder(raw_root)
        return all((folder / t).exists() or (folder / (t + ".zip")).exists() for t in self.tables or ())

    def download(self, folder: Path) -> None:
        files = fetch_cldf(self.repo, self.ref, self.metadata_path, self.tables, folder)
        write_source_info(folder, source=self.source_id, repo=self.repo, ref=self.ref, files=files)

    def dataset(self, folder: Path) -> Dataset:
        return Dataset(folder / posixpath.basename(self.metadata_path))

    def concepticon(self, writer: Writer, node_id: str, concepticon_id) -> None:
        """Record the source's own link to a Concepticon concept set as an imported mapping."""
        if concepticon_id not in (None, "", "0"):
            writer.mapping(node_id, make_node_id("concepticon", concepticon_id))


class ManualSourceMissing(RuntimeError):
    """A manual source whose files have not been added yet."""


class ManualLoader(Loader):
    """A source that cannot be downloaded automatically (a licence, a sign-up, a manual download).

    The user adds the file once with `semalingo add-file <source> <path>`; it is copied into
    the raw layer under the expected name and checksummed like any download.
    """

    files: ClassVar[tuple[str, ...]]
    instructions: ClassVar[str] = "see the notes for this source in sources.yaml"

    def download(self, folder: Path) -> None:
        missing = [name for name in self.files if not (folder / name).exists()]
        if missing:
            raise ManualSourceMissing(
                f"{self.source_id} needs a manual download ({self.instructions}). "
                f"Add it with: semalingo add-file {self.source_id} <path to {missing[0]}>"
            )

    def add_file(self, raw_root: Path, path: Path, name: str | None = None) -> Path:
        """Copy a downloaded file into the raw layer and checksum it."""
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"not a file: {path}")
        if name is None:
            if len(self.files) != 1 and path.name not in self.files:
                raise ValueError(f"{self.source_id} expects {', '.join(self.files)}; pass --as <name>")
            name = path.name if path.name in self.files else self.files[0]
        if name not in self.files:
            raise ValueError(f"{self.source_id} expects {', '.join(self.files)}, not {name}")
        folder = self.raw_folder(raw_root)
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, folder / name)
        added = sorted(n for n in self.files if (folder / n).exists())
        write_source_info(folder, source=self.source_id, ref=self.ref, files=added, added_from=path.name)
        write_checksums(folder)
        return folder / name
