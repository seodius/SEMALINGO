"""MCP server (step 7): the operations library (semalingo.ops) as tools for Claude and other LLM clients.

    semalingo mcp --db data/semalingo.duckdb

It speaks MCP over stdio and opens the database read-only (DuckDB without access to files or the
network from SQL), so the client can look things up but never change them. Every tool returns
JSON with provenance: the sources (and versions and licences) behind the answer, and how the
mappings it used were made.

Needs the MCP Python SDK: pip install "semalingo[mcp]".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from ..ops import Graph

INSTRUCTIONS = """\
SEMALINGO joins linguistic datasets in one graph: Concepticon concept sets and the words concept
lists use for them, Lexibank word lists (5,500 varieties), CLICS colexifications, DatSemShift
semantic shifts, Open English WordNet, SUMO, NoRaRe norms (age of acquisition, concreteness,
valence, ... in many languages), SUBTLEX and childLex frequencies, Wiktionary (Kaikki), Glottolog,
and word lists such as Basic English and the NSM primes.

- Node ids are "<source>:<local id>": concepticon:1248 (EYE), oewn:oewn-05318579-n (a WordNet
  synset), sumo:Eye, clics:eye, lexibank:form/... Find ids with `lookup` first.
- Concepticon concept sets are the pivot between sources; most tools accept any node and follow
  its mappings.
- Languages are Glottocodes (stan1293 English, dutc1256 Dutch, stan1295 German); ISO codes ("nl",
  "nld") and English names work too.
- Mappings between sources say how they were made: imported (by the source), manual (reviewed,
  with a reviewer), gloss (an automatic proposal from matching names), llm. Prefer imported and
  manual; say so when an answer rests on gloss proposals.
- Lexibank forms are phonetic transcriptions; Concepticon's words are the glosses concept lists use.
- Cite the provenance each result gives: source names and versions.
"""


def open_db(path: str | Path):
    """A read-only connection: DuckDB (without file or network access from SQL) or, for tests, SQLite."""
    path = str(path)
    if path.endswith((".sqlite", ".sqlite3", ".db")):
        import sqlite3

        return sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    import duckdb

    return duckdb.connect(path, read_only=True, config={"enable_external_access": False})


def build_server(graph: Graph):
    try:
        from mcp.server.mcpserver import MCPServer as Server  # MCP SDK 2.x
    except ImportError:  # pragma: no cover - SDK 1.x
        from mcp.server.fastmcp import FastMCP as Server
    from mcp.types import ToolAnnotations

    server = Server("semalingo", instructions=INSTRUCTIONS)
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read_only)
    def lookup(query: str, language: str | None = None, limit: int = 25) -> dict[str, Any]:
        """Find nodes by name or written form in every source: concepts whose name is the query
        (EYE, EYE (ORGAN)), and words written that way with the concepts they express or are
        matched to. Give a node id ("concepticon:1248") to describe that node instead: its
        properties, mappings and edges counted by type. `language` limits the words to one language."""
        return graph.lookup(query, language=language, limit=limit)

    @server.tool(annotations=read_only)
    def neighbours(node: str, hops: int = 1, edge_types: list[str] | None = None, direction: str = "both",
                   language: str | None = None, limit: int = 50) -> dict[str, Any]:
        """Nodes linked to a node, up to `hops` (max 4), through relations (subclass_of,
        hypernym, holo_part, expresses, colexification, partof, broader, ...) and mappings
        ("mapping" or "mapping:exact", "mapping:close", ...). `direction`: out (node is the
        subject: Eye subclass_of Organ), in, or both. Walk up a hierarchy with
        edge_types=["subclass_of"] (SUMO) or ["hypernym"] (WordNet), direction="out", hops=4.
        `language` keeps only words of that language. List membership ("in_list") and
        Concepticon's co-listing ("linked") are left out unless named in edge_types."""
        return graph.neighbours(node, hops=hops, edge_types=edge_types, direction=direction, language=language, limit=limit)

    @server.tool(annotations=read_only)
    def norms(node: str, constructs: list[str] | None = None, language: str | None = None,
              limit: int = 80) -> dict[str, Any]:
        """Measured values for a concept or word: age of acquisition, frequency (Zipf), concreteness,
        familiarity, imageability, valence, arousal, borrowability, ... from the node itself, nodes
        mapped to it and the words that express it, each with its source, language and route.
        Without `constructs` it shows a few values of the common constructs and counts all;
        name constructs (["aoa"], ["frequency", "concreteness"]) to get every value of them."""
        return graph.norms(node, constructs=constructs, language=language, limit=limit)

    @server.tool(annotations=read_only)
    def colexifications(concept: str, limit: int = 25) -> dict[str, Any]:
        """Concepts that languages express with the same word as this one (CLICS: number of
        language families) and attested semantic shifts from or to it (DatSemShift: polysemy or
        derivation, number of families). Accepts a Concepticon id or a node mapped to one."""
        return graph.colexifications(concept, limit=limit)

    @server.tool(annotations=read_only)
    def path(from_node: str, to_node: str, max_hops: int = 4, edge_types: list[str] | None = None) -> dict[str, Any]:
        """The shortest connections between two nodes (undirected, up to `max_hops`, max 6), with
        every edge used and how mappings on the way were made. Example: concepticon:1248 to
        sumo:Eye goes Concepticon -> WordNet -> CILI -> WordNet 3.0 <- SUMO."""
        return graph.path(from_node, to_node, max_hops=max_hops, edge_types=edge_types)

    @server.tool(annotations=read_only)
    def compare(node_a: str, node_b: str) -> dict[str, Any]:
        """Two nodes side by side: their norms (a couple of values per construct), edges counted by
        type, shared neighbours, the shortest connection, and in how many language families one
        word covers both (CLICS)."""
        return graph.compare(node_a, node_b)

    @server.tool(annotations=read_only)
    def words(concept: str, language: str | None = None, limit: int = 25) -> dict[str, Any]:
        """The words languages use for a concept, from every source: Concepticon's list glosses,
        Lexibank forms (phonetic), NoRaRe's words, WordNet lemmas through reviewed mappings, and
        words matched to the concept by gloss. One language, or the languages with most words."""
        return graph.words(concept, language=language, limit=limit)

    @server.tool(annotations=read_only)
    def sources() -> dict[str, Any]:
        """The loaded sources with their version and licence."""
        return graph.sources()

    @server.tool(annotations=read_only)
    def sql(query: str, limit: int = 200) -> dict[str, Any]:
        """A read-only SQL query (one SELECT, WITH or DESCRIBE) on the core tables, for questions the
        other tools do not cover. Tables: sources, languages(glottocode, name, family_name,
        macroarea, ...), forms(form_id, source_id, language, written_form), concepts(concept_id,
        source_id, kind, gloss), relations(source_id, from_id, to_id, relation_type, weight),
        properties(node_id, source_id, property, value_num, value_text), property_types(source_id,
        property, construct, statistic, language, description), mappings(from_id, to_id,
        mapping_type, confidence, method, reviewer, reviewed_at). At most 500 rows."""
        return graph.sql(query, limit=limit)

    return server


def serve(db: str | Path) -> None:
    if not Path(db).exists():
        sys.exit(f"No database at {db}: build one with `semalingo build` or pass --db")
    build_server(Graph(open_db(db))).run("stdio")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="semalingo-mcp", description="SEMALINGO MCP server (stdio)")
    parser.add_argument("--db", default="data/semalingo.duckdb")
    serve(parser.parse_args(argv).db)


if __name__ == "__main__":
    main()
