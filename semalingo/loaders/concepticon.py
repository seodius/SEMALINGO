"""Concepticon: concept sets, concept lists, the relations between concept sets, and the words
that the concept lists use for each concept set, in 56 languages.

Node ids: concept sets are "concepticon:<id>", concept lists "concepticon:list/<list id>",
words "concepticon:gloss/<gloss id>" (forms, with "expresses" to their concept set and
"in_list" to the list they come from).
"""

from __future__ import annotations

from collections import Counter

from ..cldf import to_float
from .base import CLDFLoader, register


@register
class ConcepticonLoader(CLDFLoader):
    source_id = "concepticon"
    repo = "concepticon/concepticon-cldf"
    ref = "v3.4.2"
    metadata_path = "cldf/Wordlist-metadata.json"
    tables = ("concepticon.csv", "conceptlists.csv", "concepts.csv", "parameter_network.csv", "languages.csv", "glosses.csv")

    def read(self, folder, writer):
        data = self.dataset(folder)

        for row in data.table("ParameterTable"):
            if row["ID"] == "0":  # placeholder for "not yet mapped"
                continue
            node = self.node(row["ID"])
            writer.concept(node, "concept", row.get("Name"))
            writer.prop(node, "definition", row.get("Description"))
            writer.prop(node, "semantic_field", row.get("Semantic_Field"))
            writer.prop(node, "ontological_category", row.get("Ontological_Category"))
            writer.prop(node, "replaced_by", row.get("Replacement_ID"))

        for row in data.table("ContributionTable"):
            node = self.node(f"list/{row['ID']}")
            writer.concept(node, "list", row.get("Name"))
            writer.prop(node, "year", to_float(row.get("Year")))
            writer.prop(node, "number_of_items", to_float(row.get("Number_Of_Items")))
            writer.prop(node, "tags", row.get("Tags"))

        # Which concept sets each list contains.
        item_list = {}
        for row in data.table("concepts.csv"):
            item_list[row["ID"]] = row["Conceptlist_ID"]
            if row.get("Concepticon_ID") in (None, "0"):
                continue
            writer.relation(self.node(row["Concepticon_ID"]), self.node(f"list/{row['Conceptlist_ID']}"), "in_list")

        # The words each list uses for its concepts (English and 55 other languages).
        languages = {row["ID"]: row.get("Glottocode") or row["ID"] for row in data.table("LanguageTable")}
        for row in data.table("FormTable"):
            node = self.node(f"gloss/{row['ID']}")
            writer.form(node, languages.get(row["Language_ID"], row["Language_ID"]), (row.get("Form") or "").strip())
            if row.get("Parameter_ID") not in (None, "", "0"):
                writer.relation(node, self.node(row["Parameter_ID"]), "expresses")
            if row.get("Concept_ID") in item_list:
                writer.relation(node, self.node(f"list/{item_list[row['Concept_ID']]}"), "in_list")

        # Relations between concept sets; the weight counts how many rows support the edge.
        edges = Counter()
        for row in data.table("ParameterNetwork"):
            relation = (row.get("relation") or row.get("Description") or "related").lower()
            edges[(row["Source_Parameter_ID"], row["Target_Parameter_ID"], relation)] += 1
        for (source, target, relation), count in edges.items():
            writer.relation(self.node(source), self.node(target), relation, float(count))
