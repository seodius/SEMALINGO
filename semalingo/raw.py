"""The pinned raw layer: data/raw/<source id>/<version>/ plus a checksum manifest.

Every download lands in its own versioned folder with a SHA256SUMS file, so a build can
check it is working from exactly the files it was built from.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

MANIFEST = "SHA256SUMS"
CHUNK = 1 << 20


def raw_dir(root: Path, source_id: str, version: str) -> Path:
    return Path(root) / source_id / version


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _data_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.name != MANIFEST)


def write_checksums(folder: Path) -> Path:
    """Write SHA256SUMS for every file under folder (in `sha256sum` format) and return its path."""
    folder = Path(folder)
    lines = [f"{sha256(p)}  {p.relative_to(folder).as_posix()}" for p in _data_files(folder)]
    manifest = folder / MANIFEST
    manifest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return manifest


def verify_checksums(folder: Path) -> list[str]:
    """Return problems found (changed, missing or unlisted files); empty means all files match."""
    folder = Path(folder)
    manifest = folder / MANIFEST
    if not manifest.exists():
        return [f"no {MANIFEST} in {folder}"]
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split("  ", 1)
            expected[name] = digest
    actual = {p.relative_to(folder).as_posix(): p for p in _data_files(folder)}
    problems = []
    for name, digest in expected.items():
        if name not in actual:
            problems.append(f"missing: {name}")
        elif sha256(actual[name]) != digest:
            problems.append(f"changed: {name}")
    problems += [f"not in manifest: {name}" for name in sorted(set(actual) - set(expected))]
    return problems
