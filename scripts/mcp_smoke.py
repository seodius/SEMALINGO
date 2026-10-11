"""Start the MCP server on a real database and ask it a few questions over stdio.

    python scripts/mcp_smoke.py data/semalingo.duckdb

Prints one line per call (tool, time, a short answer); exits 1 when a call fails.
"""

import asyncio
import json
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CALLS = [
    ("lookup", {"query": "eye"}),
    ("words", {"concept": "concepticon:256", "language": "nl"}),
    ("norms", {"node": "concepticon:1248", "constructs": ["aoa"]}),
    ("colexifications", {"concept": "concepticon:1673", "limit": 3}),
    ("path", {"from_node": "concepticon:1248", "to_node": "sumo:Eye"}),
    ("neighbours", {"node": "sumo:Food", "edge_types": ["subclass_of"], "direction": "out", "hops": 4}),
    ("sql", {"query": "SELECT source_id, COUNT(*) AS n FROM concepts GROUP BY source_id ORDER BY n DESC LIMIT 3"}),
]


def payload(result):
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


def short(name, data):
    if name == "lookup":
        return f"{data.get('concepts_total')} concepts, {data.get('words_total')} words"
    if name == "words":
        return ", ".join(w["word"] for lang in data.get("languages", []) for w in lang["words"][:5])
    if name == "norms":
        return f"{data.get('total')} values, e.g. " + "; ".join(f"{v['value']} ({v['source']}, {v.get('language')})" for v in data.get("values", [])[:3])
    if name == "colexifications":
        return ", ".join(f"{c['label']} {c['families']}" for c in data.get("clics", []))
    if name == "path":
        return " | ".join(" -> ".join(p["route"]) for p in data.get("paths", [])) or "no path"
    if name == "neighbours":
        return " > ".join(n["label"] for n in data.get("nodes", []))
    if name == "sql":
        return str(data.get("rows"))
    return str(data)[:120]


async def main(db: str) -> int:
    params = StdioServerParameters(command="semalingo", args=["mcp", "--db", db])
    failed = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(f"{len(tools.tools)} tools: {', '.join(t.name for t in tools.tools)}")
            for name, arguments in CALLS:
                start = time.time()
                result = await session.call_tool(name, arguments)
                seconds = time.time() - start
                if getattr(result, "isError", False) or getattr(result, "is_error", False):
                    failed += 1
                    print(f"{name}: ERROR {result.content[0].text[:300]}")
                    continue
                data = payload(result)
                data = data.get("result", data) if isinstance(data, dict) and set(data) == {"result"} else data
                if isinstance(data, dict) and data.get("error"):
                    failed += 1
                print(f"{name} ({seconds:.2f}s): {short(name, data)[:300]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "data/semalingo.duckdb")))
