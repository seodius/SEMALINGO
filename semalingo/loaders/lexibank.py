"""Lexibank (lexibank-analysed): word forms for 3,205 concepts in 5,501 language varieties.

Node ids:
- concepts "lexibank:<concept id>" (kind "concept"), mapped to Concepticon;
- varieties "lexibank:variety/<language id>" (kind "list": the word list of one variety from
  one dataset), with Glottocode, family, macroarea and coordinates as properties, plus the
  per-variety lexical and phonological features Lexibank computes (e.g. EyeInTear: whether the
  word for "tear" contains the word for "eye"; SyllableStructure; MotherWithM);
- forms "lexibank:form/<form id>" with the variety's Glottocode as language, "expresses" to
  their concept and "in_list" to their variety, and the segmented form ("segments", with "+"
  at morpheme boundaries where the source marks them).
"""

from __future__ import annotations

from pathlib import Path

from ..cldf import Dataset, to_float
from ..fetch import fetch_cldf, write_source_info
from .base import CLDFLoader, register

METADATA = {
    "wordlist": ("cldf/wordlist-metadata.json", ("forms.csv", "concepts.csv", "languages.csv")),
    "lexicon": ("cldf/lexicon-metadata.json", ("lexicon-values.csv", "lexicon-features.csv", "lexicon-codes.csv")),
    "phonology": ("cldf/phonology-metadata.json", ("phonology-values.csv", "phonology-features.csv", "phonology-codes.csv")),
}
FLAGS = {"True": 1.0, "False": 0.0}
VARIETY_PROPERTIES = {
    "Glottocode": "glottocode", "Family": "family", "Macroarea": "macroarea", "Latitude": "latitude",
    "Longitude": "longitude", "Dataset": "dataset", "Incollections": "collections", "Subgroup": "subgroup",
}


@register
class LexibankLoader(CLDFLoader):
    source_id = "lexibank"
    repo = "lexibank/lexibank-analysed"
    ref = "v2.2.6"
    metadata_path = METADATA["wordlist"][0]
    tables = tuple(t for _, tables in METADATA.values() for t in tables)

    def download(self, folder: Path) -> None:
        files: list[str] = []
        for metadata_path, tables in METADATA.values():
            files += [f for f in fetch_cldf(self.repo, self.ref, metadata_path, tables, folder) if f not in files]
        write_source_info(folder, source=self.source_id, repo=self.repo, ref=self.ref, files=files)

    def read(self, folder, writer):
        wordlist = Dataset(folder / "wordlist-metadata.json")

        for row in wordlist.table("ParameterTable"):
            node = self.node(row["ID"])
            writer.concept(node, "concept", row.get("Name"))
            writer.prop(node, "central_concept", row.get("Central_Concept"))
            writer.prop(node, "core_lists", row.get("Core_Concept"))
            self.concepticon(writer, node, row.get("Concepticon_ID"))

        glottocodes = {}
        for row in wordlist.table("LanguageTable"):
            node = self.node(f"variety/{row['ID']}")
            glottocodes[row["ID"]] = row.get("Glottocode") or row.get("ISO639P3code") or row["ID"]
            writer.concept(node, "list", row.get("Name"))
            for column, name in VARIETY_PROPERTIES.items():
                value = row.get(column)
                writer.prop(node, name, to_float(value) if name in ("latitude", "longitude") else value)

        for row in wordlist.table("FormTable"):
            node = self.node(f"form/{row['ID']}")
            writer.form(node, glottocodes.get(row["Language_ID"], row["Language_ID"]), row.get("Form") or "")
            writer.relation(node, self.node(row["Parameter_ID"]), "expresses")
            writer.relation(node, self.node(f"variety/{row['Language_ID']}"), "in_list")
            segments = row.get("Segments")
            writer.prop(node, "segments", " ".join(segments) if isinstance(segments, list) else segments)

        for part in ("lexicon", "phonology"):
            data = Dataset(folder / f"{part}-metadata.json")
            codes: dict[str, list[str]] = {}
            for row in data.table("CodeTable"):
                value = row["ID"][len(row["Parameter_ID"]) + 1:]
                if value not in ("None", "True", "False"):
                    codes.setdefault(row["Parameter_ID"], []).append(f"{value} = {row.get('Name')}")
            for row in data.table("ParameterTable"):
                text = f"{row.get('Name') or ''}. {row.get('Description') or ''}"
                if codes.get(row["ID"]):
                    text += " Codes: " + "; ".join(codes[row["ID"]])
                writer.property_type(
                    row["ID"], construct=f"{part} feature", category="norms", method="computed from word lists",
                    description=" ".join(text.split()).strip(" ."),
                )
            for row in data.table("ValueTable"):
                value = FLAGS.get(row.get("Value"), row.get("Value"))
                if value in (None, "", "?"):
                    continue  # not enough data in this variety
                number = to_float(value)
                writer.prop(self.node(f"variety/{row['Language_ID']}"), row["Parameter_ID"], number if number is not None else value)
