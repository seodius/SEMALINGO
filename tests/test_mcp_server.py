"""The MCP server (step 7), spoken to over stdio by an MCP client, on a fixture database."""

import asyncio
import json
import sqlite3
import sys
import unittest
from pathlib import Path

from tests.test_loaders import LoaderTestCase

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # pragma: no cover - the MCP SDK is an optional dependency
    ClientSession = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(ClientSession is None, "the MCP SDK is not installed (pip install semalingo[mcp])")
class McpServerTest(LoaderTestCase):
    def setUp(self):
        super().setUp()
        for source in ("concepticon", "sumo", "clics"):
            self.load(source)
        self.db = Path(self.tmp.name) / "fixture.sqlite"
        target = sqlite3.connect(self.db)
        self.conn.backup(target)
        target.close()

    async def session_calls(self, calls):
        params = StdioServerParameters(command=sys.executable, args=["-m", "semalingo.mcp_server", "--db", str(self.db)],
                                       cwd=str(ROOT))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                results = [await session.call_tool(name, arguments) for name, arguments in calls]
        return tools, results

    @staticmethod
    def payload(result):
        if getattr(result, "structuredContent", None):
            content = result.structuredContent
            return content.get("result", content) if set(content) == {"result"} else content
        return json.loads(result.content[0].text)

    def test_tools_answer_with_provenance(self):
        tools, (lookup, hierarchy, colex, refused) = asyncio.run(self.session_calls([
            ("lookup", {"query": "eye"}),
            ("neighbours", {"node": "sumo:Eye", "edge_types": ["subclass_of"], "direction": "out", "hops": 2}),
            ("colexifications", {"concept": "concepticon:1409"}),
            ("sql", {"query": "DELETE FROM concepts"}),
        ]))
        names = {t.name for t in tools.tools}
        self.assertEqual(names, {"lookup", "neighbours", "norms", "colexifications", "path", "compare", "words", "sources", "sql"})
        read_only = [getattr(t.annotations, "read_only_hint", None) or getattr(t.annotations, "readOnlyHint", None)
                     for t in tools.tools]  # the attribute name differs between SDK 1.x and 2.x
        self.assertTrue(all(read_only))
        found = self.payload(lookup)
        self.assertIn("concepticon:1209", [c["id"] for c in found["concepts"]])
        self.assertIn("concepticon", [s["id"] for s in found["provenance"]["sources"]])
        self.assertEqual([n["id"] for n in self.payload(hierarchy)["nodes"]], ["sumo:Organ", "sumo:AnimalAnatomicalStructure"])
        self.assertEqual(self.payload(colex)["clics"][0]["families"], 12)
        self.assertIn("error", self.payload(refused))
        # the database is opened read-only: nothing was deleted
        check = sqlite3.connect(self.db)
        self.addCleanup(check.close)
        self.assertEqual(check.execute("SELECT COUNT(*) FROM concepts").fetchone()[0], self.value("SELECT COUNT(*) FROM concepts"))
