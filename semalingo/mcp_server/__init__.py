"""MCP server (step 7): exposes the six operations in `semalingo.ops` to LLMs and agents.

The server calls only the operations library, never raw queries, and passes every
result's provenance through to the caller.
"""
