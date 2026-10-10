"""Generate registry entries for the datasets in Open Lexicon (github.com/chrplr/openlexicon).

Usage:
    git clone --depth 1 https://github.com/chrplr/openlexicon.git
    python scripts/import_openlexicon.py openlexicon > openlexicon-entries.yaml

Reads each dataset folder's readme and the JSON descriptors in datasets-info/_json, and
prints one sources.yaml entry per dataset. Datasets already in the registry are skipped.
Licences are only filled in where a readme or licence file in the dataset's own folder
states one (LICENCES below); everything else stays TODO for a manual check.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = "chrplr/openlexicon"
NOT_DATASETS = {"_json", "json2md", "links", "list-of-datasets", "images"}
ALREADY_IN_REGISTRY = {"SUBTLEX-US": "subtlex-us", "AoA-32lang": "aoa-32lang", "Morpholex-en": "morpholex-en", "WorldLex": "worldlex"}
# Folders that hold an older copy of another folder's dataset.
DUPLICATES = {"chacqfam": "AoA_FamConcept_1225", "Lete_2004_Manulex": "Manulex"}
# Licences stated in the dataset's own folder (readme text or a LICENSE file), checked by hand.
LICENCES = {
    "Chronolex": "CC BY-SA 4.0",
    "FrenchLexiconProject": "CC BY-SA 4.0",
    "Lexique382": "CC BY-SA 4.0",
    "Lexique383": "CC BY-SA 4.0",
    "Lexique-Infra": "CC BY-SA 4.0",
    "Megalex": "CC BY-SA 4.0",
    "Voisins": "CC BY-SA",
    "Morphalou": "Lesser General Public License For Linguistic Resources (LGPL-LR)",
    "Dicollecte": "Mozilla Public License 2.0",
}
DATA_SUFFIXES = (".tsv", ".csv", ".txt", ".xls", ".xlsx", ".rds", ".Rdata", ".zip")
# Where Open Lexicon's readme text describes a different dataset than the folder holds.
NOTE_OVERRIDES = {
    "Manulex": "French word frequencies from primary-school reading books, by grade (Lété, Sprenger-Charolles & Colé 2004). Open Lexicon's readme for this folder carries the description of another dataset.",
}
NOT_DOWNLOADS = ("chrplr.github.io", "/shiny/", "lgpllr", "www.atilf.fr")
# Where a descriptor's checksum cannot be trusted.
VERSION_OVERRIDES = {
    "Lexique-Infra": "TODO (Open Lexicon's descriptor repeats Lexique382's md5 for this file)",
}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def readme_of(folder: Path) -> str:
    candidates = sorted(folder.glob("README*.md")) + sorted(folder.glob("*.md")) + sorted(folder.glob("README*.txt")) + sorted(folder.glob("Readme*.txt"))
    for path in candidates:
        return path.read_text(encoding="utf-8", errors="replace")
    return ""


def first_paragraph(text: str) -> str:
    for block in re.split(r"\n\s*\n", text):
        line = " ".join(block.split())
        if line and not line.startswith(("#", "**", "Table", "File", "Online", "[", "-", "=")):
            return re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)[:300]
    return ""


def title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("#"):
            title = line.strip("# ").strip()
            if title:
                return title
    return fallback


def website_of(text: str) -> str | None:
    match = re.search(r"\*\*Web ?site:?\*\*:?\s*\[?[^\]\n<(]*\]?\(?<?(https?://[^\s)>]+)", text, re.I)
    return match.group(1) if match else None


def descriptors(root: Path) -> dict[str, list[dict]]:
    """Descriptor dicts grouped by the dataset folder they belong to."""
    folders = {p.name for p in (root / "datasets-info").iterdir() if p.is_dir()}
    grouped: dict[str, list[dict]] = {}
    for path in sorted((root / "datasets-info" / "_json").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        readme = (data.get("readme") or "").split("datasets-info/")[-1]
        folder = readme.split("/")[0] if "/" in readme else path.stem
        if folder not in folders:
            folder = next((f for f in folders if path.stem.startswith(f)), path.stem)
        grouped.setdefault(folder, []).append(data)
    return grouped


def tracked_files(root: Path, folder: str) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "--name-only", "HEAD", f"datasets-info/{folder}/"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [Path(line).name for line in out.splitlines()]


def readme_download(text: str) -> str | None:
    """The readme's most likely data link: a data file, else a supplementary file, else another page."""
    urls = [u.rstrip(".,") for u in re.findall(r"https?://[^\s)>\"']+", text)]
    urls = [u for u in urls if not any(bad in u for bad in NOT_DOWNLOADS)]
    for test in (lambda u: u.endswith(DATA_SUFFIXES), lambda u: ".s00" in u, lambda u: "doi.org" not in u):
        match = next((u for u in urls if test(u)), None)
        if match:
            return match
    return None


def used_by(folder: str, text: str) -> list[str]:
    if "assoc" in folder.lower():
        return ["Q4"]
    key = (folder + " " + text[:400]).lower()
    if any(k in key for k in ("aoa", "acquisition", "enfant", "manulex", "children")):
        return ["Q1", "Q3a"]
    if any(k in key for k in ("freq", "imag", "concr", "famil", "lexique", "subtlex", "valem", "sensory")):
        return ["Q1"]
    return []


def entry(root: Path, folder: str, descs: list[dict], commit: str, duplicate_of_me: str | None) -> dict:
    text = readme_of(root / "datasets-info" / folder)
    description = first_paragraph(text) or (descs[0].get("description") if descs else "") or ""
    urls = [u for d in descs for u in d.get("urls", [])]
    own = [u for u in urls if slug(folder) in slug(Path(u["url"]).name)]
    pool = own or urls
    main = next((u for u in pool if u["url"].endswith((".tsv", ".csv", ".txt"))), pool[0] if pool else None)
    tags = sorted({t for d in descs for t in d.get("tags", []) if t not in ("frequencies",)})
    files = [f for f in tracked_files(root, folder) if f.endswith(DATA_SUFFIXES) and not f.lower().startswith(("readme", "license"))]
    tree = f"https://github.com/{REPO}/tree/{commit}/datasets-info/{folder}"

    if main:
        download = main["url"]
        version = f"Open Lexicon copy, md5 {main['md5sum']}" if main.get("md5sum") else f"Open Lexicon commit {commit[:7]}"
        fmt = Path(main["url"]).suffix.lstrip(".").upper() or "TODO"
        if len(urls) > 1:
            fmt += f" ({len(urls)} files: " + ", ".join(Path(u["url"]).name for u in urls) + ")"
    elif files:
        download = tree
        version = f"Open Lexicon commit {commit[:7]}"
        fmt = ", ".join(files)
    elif readme_download(text):
        download = readme_download(text)
        suffix = Path(download).suffix.lstrip(".").upper()
        version, fmt = "TODO", suffix if suffix in {x.lstrip(".").upper() for x in DATA_SUFFIXES} else "TODO"
    else:
        download, version, fmt = "TODO", "TODO", "TODO"

    version = VERSION_OVERRIDES.get(folder, version)
    licence = LICENCES.get(folder, "TODO")
    notes = NOTE_OVERRIDES.get(folder, description)
    if tags:
        notes += f" Tags: {', '.join(tags)}."
    if duplicate_of_me:
        notes += f" An older copy sits in the {duplicate_of_me} folder."
    if licence == "TODO":
        notes += " No licence in the dataset's own folder; Open Lexicon's repository default is CC BY-SA 4.0 unless a folder says otherwise."
    notes += " Listed in Open Lexicon."

    return {
        "id": slug(folder),
        "name": f"{title_of(text, folder)} (Open Lexicon)",
        "wave": "second",
        "unit": "associations" if "assoc" in folder.lower() else "forms",
        "homepage": website_of(text) or (descs[0].get("website") if descs and descs[0].get("website") else tree),
        "download": download,
        "format": fmt,
        "version": version,
        "licence": licence,
        "redistributable": "yes" if licence != "TODO" else "TODO",
        "used_by": used_by(folder, text),
        "checked": False,
        "notes": " ".join(notes.split()),
    }


def main(root: Path) -> None:
    commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    grouped = descriptors(root)
    folders = sorted(p.name for p in (root / "datasets-info").iterdir() if p.is_dir() and p.name not in NOT_DATASETS)
    duplicate_of = {v: k for k, v in DUPLICATES.items()}
    entries = [
        entry(root, folder, grouped.get(folder, []), commit, duplicate_of.get(folder))
        for folder in folders
        if folder not in ALREADY_IN_REGISTRY and folder not in DUPLICATES
    ]
    print(f"  # ---------- Open Lexicon collection (generated by scripts/import_openlexicon.py from commit {commit[:7]}) ----------\n")
    text = yaml.safe_dump(entries, sort_keys=False, allow_unicode=True, width=100)
    print("\n".join(("  " + line) if line else line for line in text.splitlines()).replace("\n  - id:", "\n\n  - id:"))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
