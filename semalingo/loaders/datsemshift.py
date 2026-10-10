"""DatSemShift (CLDF edition): concepts and the semantic shifts between them.

Node ids: "datsemshift:<parameter id>". Each concept's Target_Concepts column lists the
concepts its words shifted to, with counts of language families for two kinds of shift:
polysemy (one word, both meanings) and derivation (a derived word carries the new meaning).
They become directed relations "shift_polysemy" and "shift_derivation", weighted by families.
"""

from __future__ import annotations

import json

from .base import CLDFLoader, register


def targets(cell) -> list[dict]:
    if not cell:
        return []
    try:
        value = json.loads(cell)
    except (TypeError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


@register
class DatSemShiftLoader(CLDFLoader):
    source_id = "datsemshift"
    repo = "lexibank/datsemshift"
    ref = "v1.1rc"
    tables = ("parameters.csv",)

    def read(self, folder, writer):
        data = self.dataset(folder)
        for row in data.table("ParameterTable"):
            node = self.node(row["ID"])
            writer.concept(node, "meaning", row.get("Name"))
            writer.prop(node, "domain", row.get("Domain") if row.get("Domain") not in ("N/a", "n/a") else None)
            writer.prop(node, "definition", row.get("Definition"))
            self.concepticon(writer, node, row.get("Concepticon_ID"))
            for target in targets(row.get("Target_Concepts")):
                if not target.get("ID"):
                    continue
                to_node = self.node(target["ID"])
                if target.get("PolysemyByFamily"):
                    writer.relation(node, to_node, "shift_polysemy", float(target["PolysemyByFamily"]))
                if target.get("DerivationByFamily"):
                    writer.relation(node, to_node, "shift_derivation", float(target["DerivationByFamily"]))
