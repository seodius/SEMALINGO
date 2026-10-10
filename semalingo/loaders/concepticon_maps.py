"""Concepticon's gloss lookup tables (mappings/map-<language>.tsv in concepticon-data).

Concepticon builds these from all its concept lists: for each language, every gloss that a
list uses for a concept set, with PRIORITY = how many list items use that link. They are the
index for gloss matching (see semalingo.matching).

Node ids: one form per language and normalised gloss, "concepticon-maps:<iso 639-1>/<gloss>".
Each has an imported "close" mapping to every concept set the gloss is linked to; its
confidence is that concept set's share of the gloss's uses (each entry counts PRIORITY + 1, so
entries with PRIORITY 0 still count).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from ..cldf import to_float
from ..fetch import download, github_raw, is_missing, write_source_info
from ..ids import make_node_id
from ..languages import ISO1_GLOTTOCODE
from ..matching import gloss_keys
from .base import Loader, register
from .frequencies import word_id


@register
class ConcepticonMapsLoader(Loader):
    source_id = "concepticon-maps"
    repo = "concepticon/concepticon-data"
    ref = "v3.4.0"

    def download(self, folder: Path) -> None:
        files = []
        for code in sorted(ISO1_GLOTTOCODE):
            name = f"map-{code}.tsv"
            try:
                download(github_raw(self.repo, self.ref, f"mappings/{name}"), folder / name)
            except Exception as error:  # a language without a table at this release
                if is_missing(error):
                    continue
                raise
            files.append(name)
        if not files:
            raise RuntimeError(f"{self.source_id}: no lookup tables found at {self.repo}@{self.ref}")
        write_source_info(folder, source=self.source_id, repo=self.repo, ref=self.ref, files=files)

    def read(self, folder, writer):
        writer.property_type(
            "uses", construct="gloss frequency", statistic="sum", category="norms", method="concept lists",
            description="How many concept-list items use this gloss, over all concept sets it is linked to "
            "(Concepticon PRIORITY + 1 per lookup entry).",
        )
        for path in sorted(folder.glob("map-*.tsv")):
            code = path.stem[len("map-"):]
            language = ISO1_GLOTTOCODE.get(code)
            if language is None:
                continue
            uses: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
            with open(path, encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle, delimiter="\t"):
                    if row.get("ID") in (None, "", "0"):
                        continue
                    gloss = row.get("GLOSS") or ""
                    local = gloss.split("///", 1)[1] if "///" in gloss else gloss
                    weight = (to_float(row.get("PRIORITY")) or 0.0) + 1
                    for key in gloss_keys(local, language):
                        uses[key][row["ID"]] += weight
            for key, concepts in uses.items():
                node = self.node(f"{code}/{word_id(key)}")
                total = sum(concepts.values())
                writer.form(node, language, key)
                writer.prop(node, "uses", total)
                for concept_id, weight in concepts.items():
                    writer.mapping(node, make_node_id("concepticon", concept_id), "close", round(weight / total, 4))
