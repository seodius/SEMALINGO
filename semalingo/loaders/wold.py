"""WOLD: meanings with borrowability, age and simplicity scores, and the word forms behind them.

Node ids: meanings are "wold:<parameter id>", forms "wold:form/<form id>".
"""

from __future__ import annotations

from ..cldf import to_float
from .base import CLDFLoader, register


@register
class WoldLoader(CLDFLoader):
    source_id = "wold"
    repo = "lexibank/wold"
    ref = "v4.2"
    tables = ("parameters.csv", "languages.csv", "forms.csv")

    def read(self, folder, writer):
        data = self.dataset(folder)

        for row in data.table("ParameterTable"):
            node = self.node(row["ID"])
            writer.concept(node, "meaning", row.get("Name"))
            writer.prop(node, "borrowed_score", to_float(row.get("Borrowed_score")))
            writer.prop(node, "age_score", to_float(row.get("Age_score")))
            writer.prop(node, "simplicity_score", to_float(row.get("Simplicity_score")))
            writer.prop(node, "semantic_field", row.get("Semantic_field"))
            writer.prop(node, "semantic_category", row.get("Semantic_category"))
            writer.prop(node, "core_list", row.get("Core_list"))
            self.concepticon(writer, node, row.get("Concepticon_ID"))

        languages = {
            row["ID"]: row.get("Glottocode") or row.get("ISO639P3code") or f"wold-{row['ID']}"
            for row in data.table("LanguageTable")
        }
        for row in data.table("FormTable"):
            form = self.node(f"form/{row['ID']}")
            writer.form(form, languages.get(row["Language_ID"], row["Language_ID"]), row.get("Form") or row.get("Value") or "")
            writer.relation(form, self.node(row["Parameter_ID"]), "expresses")
            writer.prop(form, "borrowed_score", to_float(row.get("Borrowed_score")))
            writer.prop(form, "borrowed", row.get("Borrowed"))
