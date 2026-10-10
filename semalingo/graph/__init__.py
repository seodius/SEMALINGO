"""Graph projection (step 5): generate the graph from the core tables.

One named graph per source plus one for the mappings, rebuilt with a single command.
The target (RDF with OntoLex-Lemon + SKOS, or a Neo4j property graph) is still open;
because the graph is always generated from the tables, that choice stays reversible.
"""
