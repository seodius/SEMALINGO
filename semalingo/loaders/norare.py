"""NoRaRe: norms, ratings and relations from over a hundred studies, linked to Concepticon.

Loaded from the CLDF release (concepticon/norare-cldf, CC BY 4.0), not from the curation
repository norare-data (CC BY-NC 4.0).

Node ids: a word as one study lists it is "norare:form/<gloss id>", a concept set
"norare:concept/<concepticon id>" (mapped to "concepticon:<id>"), a study
"norare:dataset/<dataset id>". Every value is a property of the word, named after its variable
(e.g. "Kuperman-2012-AoA-ENGLISH_AOA_MEAN"); property_types says what each variable measures,
so all age-of-acquisition norms can be found through construct = 'aoa'.
"""

from __future__ import annotations

import json

from ..cldf import to_float
from .base import CLDFLoader, register

NUMERIC = {"decimal", "float", "double", "integer", "nonNegativeInteger", "positiveInteger"}


def datatype_base(spec) -> str | None:
    """The base datatype of a variable, from its CSVW datatype description."""
    try:
        kind = json.loads(spec or "{}").get("datatype")
    except (ValueError, AttributeError):
        return None
    return kind.get("base") if isinstance(kind, dict) else kind


def lower(text):
    return text.strip().lower() if isinstance(text, str) and text.strip() else None


@register
class NorareLoader(CLDFLoader):
    source_id = "norare"
    repo = "concepticon/norare-cldf"
    ref = "v1.1"
    metadata_path = "cldf/Wordlist-metadata.json"
    tables = ("concepticon.csv", "datasets.csv", "languages.csv", "variables.csv", "glosses.csv", "norare.csv")

    def read(self, folder, writer):
        data = self.dataset(folder)
        languages = {
            row["ID"]: row.get("Glottocode") or row.get("ISO639P3code") or row["ID"]
            for row in data.table("LanguageTable")
        }

        for row in data.table("ParameterTable"):
            node = self.node(f"concept/{row['ID']}")
            writer.concept(node, "concept", row.get("Name"))
            writer.prop(node, "count_datasets", to_float(row.get("count_datasets")))
            writer.prop(node, "count_variables", to_float(row.get("count_variables")))
            self.concepticon(writer, node, row.get("Concepticon_ID") or row["ID"])

        for row in data.table("ContributionTable"):
            node = self.node(f"dataset/{row['ID']}")
            writer.concept(node, "list", row.get("Name"))
            writer.prop(node, "year", to_float(row.get("Year")))
            writer.prop(node, "url", row.get("URL"))
            writer.prop(node, "citation", row.get("Citation"))

        numeric = {}
        for row in data.table("variables.csv"):
            numeric[row["ID"]] = datatype_base(row.get("Datatype")) in NUMERIC
            writer.property_type(
                row["ID"],
                construct=lower(row.get("Result")),
                aspect=row.get("Other"),
                statistic=row.get("Type"),
                category=row.get("Category"),
                method=row.get("Method"),
                language=languages.get(row.get("Language_ID"), row.get("Language_ID")),
                description=row.get("Note"),
            )

        for row in data.table("FormTable"):
            node = self.node(f"form/{row['ID']}")
            writer.form(node, languages.get(row["Language_ID"], row["Language_ID"]), row.get("Form") or "")
            if row.get("Parameter_ID"):
                writer.relation(node, self.node(f"concept/{row['Parameter_ID']}"), "expresses")
            if row.get("Dataset_ID"):
                writer.relation(node, self.node(f"dataset/{row['Dataset_ID']}"), "in_list")

        # Numeric variables become numbers; labels, word lists and JSON stay text.
        for row in data.table("norare.csv"):
            variable = row["Variable_ID"]
            value = row.get("Value")
            writer.prop(self.node(f"form/{row['Unit_ID']}"), variable, to_float(value) if numeric.get(variable) else value)
