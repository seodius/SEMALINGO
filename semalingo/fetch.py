"""Downloads into the pinned raw layer: data/raw/<source id>/<version>/.

Only standard-library HTTP is used, so fetching works in a bare Python or Docker setup.
Each fetched folder gets a SOURCE.json (what was fetched, from where, when) and a
SHA256SUMS manifest (see raw.py).
"""

from __future__ import annotations

import json
import posixpath
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .cldf import table_urls

USER_AGENT = "SEMALINGO (+https://github.com/seodius/SEMALINGO)"
RAW_GITHUB = "https://raw.githubusercontent.com"
SOURCE_INFO = "SOURCE.json"
TIMEOUT = 120


def download(url: str, dest: Path) -> Path:
    """Stream url to dest (via a .part file, so an interrupted download never looks complete)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response, open(partial, "wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    partial.replace(dest)
    return dest


def is_missing(error: Exception) -> bool:
    """True when a download failed because the file does not exist (HTTP 404 or a missing local file)."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 404
    if isinstance(error, urllib.error.URLError):
        return isinstance(error.reason, FileNotFoundError) or "No such file" in str(error.reason)
    return isinstance(error, FileNotFoundError)


def github_raw(repo: str, ref: str, path: str) -> str:
    return f"{RAW_GITHUB}/{repo}/{ref}/{path}"


def fetch_cldf(repo: str, ref: str, metadata_path: str, tables: tuple[str, ...] | None, folder: Path) -> list[str]:
    """Download a CLDF metadata file and the listed tables (all if None) at a git ref.

    Tables stored zipped in the repository ("forms.csv.zip") are found automatically.
    Returns the file names written into folder.
    """
    meta_name = posixpath.basename(metadata_path)
    base = posixpath.dirname(metadata_path)
    download(github_raw(repo, ref, metadata_path), folder / meta_name)
    metadata = json.loads((folder / meta_name).read_text(encoding="utf-8"))
    written = [meta_name]
    wanted = table_urls(metadata) if tables is None else list(tables)
    for url in wanted:
        remote = posixpath.join(base, url) if base else url
        try:
            download(github_raw(repo, ref, remote), folder / url)
            written.append(url)
        except Exception as error:  # noqa: BLE001 - narrowed by is_missing
            if not is_missing(error):
                raise
            download(github_raw(repo, ref, remote + ".zip"), folder / (url + ".zip"))
            written.append(url + ".zip")
    return written


def write_source_info(folder: Path, **info) -> Path:
    info.setdefault("fetched_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    path = folder / SOURCE_INFO
    path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
