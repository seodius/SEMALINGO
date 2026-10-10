"""Load and validate the source registry (sources.yaml)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

WAVES = ("first", "second", "parked")
UNITS = (
    "forms",
    "lemmas",
    "concepts",
    "meanings",
    "senses",
    "classes",
    "primes",
    "properties",
    "associations",
    "aggregates",
    "other",
)
REDISTRIBUTABLE = ("yes", "no", "TODO")
QUESTIONS = ("Q1", "Q3a", "Q3b", "Q4", "Q5")
REQUIRED = (
    "id",
    "name",
    "wave",
    "unit",
    "homepage",
    "download",
    "format",
    "version",
    "licence",
    "redistributable",
    "used_by",
    "checked",
    "notes",
)
# Fields that must be filled in (no TODO) before an entry may be marked checked.
VERIFIABLE = ("homepage", "download", "format", "version", "licence", "redistributable")
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
TODO = "TODO"


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    wave: str
    unit: str
    homepage: str
    download: str
    format: str
    version: str
    licence: str
    redistributable: str
    used_by: tuple[str, ...] = field(default_factory=tuple)
    checked: bool = False
    notes: str = ""

    @property
    def open_fields(self) -> list[str]:
        """Verifiable fields that are still TODO."""
        return [name for name in VERIFIABLE if getattr(self, name) == TODO]


def default_registry_path() -> Path:
    """$SEMALINGO_REGISTRY, else ./sources.yaml, else the copy next to the package (a source checkout)."""
    env = os.environ.get("SEMALINGO_REGISTRY")
    if env:
        return Path(env)
    here = Path.cwd() / "sources.yaml"
    if here.exists():
        return here
    return Path(__file__).resolve().parent.parent / "sources.yaml"


def read_raw(path: Path | None = None) -> list[dict]:
    path = path or default_registry_path()
    with open(path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    entries = data.get("sources")
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected a top-level 'sources' list")
    return entries


def validate(entries: list[dict]) -> list[str]:
    """Return a list of human-readable problems; empty means the registry is valid."""
    problems: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        label = entry.get("id", f"entry #{index + 1}") if isinstance(entry, dict) else f"entry #{index + 1}"
        if not isinstance(entry, dict):
            problems.append(f"{label}: not a mapping")
            continue
        missing = [key for key in REQUIRED if key not in entry]
        unknown = sorted(set(entry) - set(REQUIRED))
        if missing:
            problems.append(f"{label}: missing fields {', '.join(missing)}")
        if unknown:
            problems.append(f"{label}: unknown fields {', '.join(unknown)}")
        source_id = entry.get("id")
        if not isinstance(source_id, str) or not ID_PATTERN.match(source_id):
            problems.append(f"{label}: id must be a lowercase slug (letters, digits, hyphens)")
        elif source_id in seen:
            problems.append(f"{label}: duplicate id")
        else:
            seen.add(source_id)
        if entry.get("wave") not in WAVES:
            problems.append(f"{label}: wave must be one of {', '.join(WAVES)}")
        if entry.get("unit") not in UNITS:
            problems.append(f"{label}: unit must be one of {', '.join(UNITS)}")
        if str(entry.get("redistributable")) not in REDISTRIBUTABLE:
            problems.append(f"{label}: redistributable must be one of {', '.join(REDISTRIBUTABLE)}")
        used_by = entry.get("used_by", [])
        if not isinstance(used_by, list) or any(q not in QUESTIONS for q in used_by):
            problems.append(f"{label}: used_by must be a list drawn from {', '.join(QUESTIONS)}")
        if not isinstance(entry.get("checked"), bool):
            problems.append(f"{label}: checked must be true or false")
        elif entry["checked"]:
            still_open = [key for key in VERIFIABLE if str(entry.get(key)) == TODO]
            if still_open:
                problems.append(f"{label}: marked checked but still TODO: {', '.join(still_open)}")
        for key in ("name", "homepage", "download", "format", "version", "licence", "notes"):
            if key in entry and not isinstance(entry[key], str):
                problems.append(f"{label}: {key} must be text (quote it in YAML)")
    return problems


def load_registry(path: Path | None = None) -> list[Source]:
    """Read and validate the registry; raise ValueError listing every problem."""
    entries = read_raw(path)
    problems = validate(entries)
    if problems:
        raise ValueError("Invalid source registry:\n  " + "\n  ".join(problems))
    return [
        Source(
            id=e["id"],
            name=e["name"],
            wave=e["wave"],
            unit=e["unit"],
            homepage=e["homepage"],
            download=e["download"],
            format=e["format"],
            version=e["version"],
            licence=e["licence"],
            redistributable=str(e["redistributable"]),
            used_by=tuple(e["used_by"]),
            checked=e["checked"],
            notes=e["notes"],
        )
        for e in entries
    ]


def licence_table(sources: list[Source]) -> str:
    """Render DATA-LICENSES.md from the registry."""
    lines = [
        "# Data licences",
        "",
        "Generated from `sources.yaml` by `semalingo licences --write`; edit the registry, not this file.",
        "",
        "SEMALINGO's code is Apache-2.0 (see `LICENSE`). Data is not: every source keeps its own terms,",
        "raw data is never committed here, and anything derived from a share-alike or non-commercial",
        "source stays under that source's terms. \"TODO\" means the terms have not been verified yet.",
        "",
    ]
    for wave in WAVES:
        rows = [s for s in sources if s.wave == wave]
        if not rows:
            continue
        lines += [
            f"## {wave.capitalize()} wave" if wave != "parked" else "## Parked",
            "",
            "| Source | Licence | Raw data redistributable | Verified |",
            "| --- | --- | --- | --- |",
        ]
        for s in rows:
            verified = "yes" if s.checked else "no"
            lines.append(f"| {s.name} (`{s.id}`) | {s.licence} | {s.redistributable} | {verified} |")
        lines.append("")
    return "\n".join(lines)
