"""The six operations every interface (CLI, MCP server, UI) calls. Not implemented yet (step 6).

Every result carries its provenance: the sources and mapping edges it went through, so a
reader can see when an answer rests on one weak close-match edge and discard it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

__all__ = [
    "Provenance",
    "Result",
    "lookup",
    "neighbours",
    "norms",
    "colexifications",
    "path",
    "compare",
]


@dataclass(frozen=True)
class Provenance:
    sources: tuple[str, ...]
    mappings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Result:
    value: Any
    provenance: Provenance


def _todo(name: str):
    raise NotImplementedError(f"{name} is planned for step 6 (operations library)")


def lookup(conn, query: str, language: str | None = None) -> list[Result]:
    """Find nodes matching a form or concept, across all sources."""
    _todo("lookup")


def neighbours(conn, node_id: str, hops: int = 1, edge_types: Sequence[str] | None = None) -> list[Result]:
    """Nodes connected to node_id within `hops`, optionally limited to some edge types."""
    _todo("neighbours")


def norms(conn, node_id: str) -> list[Result]:
    """Frequency, age of acquisition, concreteness, borrowability, ... each with its source."""
    _todo("norms")


def colexifications(conn, concept_id: str) -> list[Result]:
    """Concepts other languages merge this concept with, with language counts."""
    _todo("colexifications")


def path(conn, from_id: str, to_id: str, max_hops: int = 4) -> list[Result]:
    """Shortest paths between two nodes, with the edges used."""
    _todo("path")


def compare(conn, a: str, b: str) -> Result:
    """Two concepts' properties and relations side by side."""
    _todo("compare")
