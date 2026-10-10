"""Node ids: every node is "<source id>:<local id>", e.g. "concepticon:1209".

Sources keep their own ids; SEMALINGO never merges nodes. Links between sources are
mapping edges (see the `mappings` table), so a node id always says where it came from.
"""

from __future__ import annotations

from .registry import ID_PATTERN

SEPARATOR = ":"


def make_node_id(source_id: str, local_id: str | int) -> str:
    if not ID_PATTERN.match(source_id):
        raise ValueError(f"not a valid source id: {source_id!r}")
    local = str(local_id).strip()
    if not local:
        raise ValueError("local id must not be empty")
    if any(ch.isspace() for ch in local):
        raise ValueError(f"local id must not contain whitespace: {local!r}")
    return f"{source_id}{SEPARATOR}{local}"


def split_node_id(node_id: str) -> tuple[str, str]:
    """Return (source id, local id). The local id may itself contain ':'."""
    source_id, sep, local = node_id.partition(SEPARATOR)
    if not sep or not local or not ID_PATTERN.match(source_id):
        raise ValueError(f"not a valid node id: {node_id!r}")
    return source_id, local
