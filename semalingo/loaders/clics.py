"""CLICS4: concepts and the colexification network between them.

Node ids: "clics:<concept id>". CLICS names colexified concepts by their Concepticon
gloss, so edges are resolved through the concepts table. Colexification is undirected:
each edge is stored once, weighted by the number of language families that colexify
the pair (CLICS's own robustness measure).
"""

from __future__ import annotations

from ..cldf import to_float
from .base import CLDFLoader, register


@register
class ClicsLoader(CLDFLoader):
    source_id = "clics"
    repo = "clics/clics4"
    ref = "v1.0"
    metadata_path = "cldf/StructureDataset-metadata.json"
    tables = ("concepts.csv", "colexifications.csv")

    def read(self, folder, writer):
        data = self.dataset(folder)

        by_gloss = {}
        for row in data.table("concepts.csv"):
            node = self.node(row["ID"])
            gloss = row.get("Concepticon_Gloss") or row.get("Name")
            if gloss:
                by_gloss[gloss] = node
            writer.concept(node, "concept", gloss)
            writer.prop(node, "family_count", to_float(row.get("Family_Count")))
            writer.prop(node, "language_count", to_float(row.get("Language_Count")))
            writer.prop(node, "community", row.get("Community"))
            self.concepticon(writer, node, row.get("Concepticon_ID"))

        unresolved = 0
        for row in data.table("colexifications.csv"):
            source = by_gloss.get(row.get("Source_Concept"))
            target = by_gloss.get(row.get("Target_Concept"))
            if not source or not target:
                unresolved += 1
                continue
            writer.relation(source, target, "colexification", to_float(row.get("Family_Count")))
        self.unresolved = unresolved
