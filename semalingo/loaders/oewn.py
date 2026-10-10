"""Open English WordNet from its WN-LMF XML release.

Node ids: synsets are "oewn:<synset id>" (kind "sense"), lexical entries "oewn:entry/<entry id>"
(forms, language English, Glottocode stan1293). Relations: entry -> synset "sense_of"; synset -> synset by WordNet
relation type (hypernym, part_holonym, ...); entry -> entry for sense relations such as
derivation and antonym, so derivational families and opposites can be followed.
"""

from __future__ import annotations

import gzip
import xml.etree.ElementTree as ET
from pathlib import Path

from ..fetch import download, write_source_info
from ..languages import ENGLISH
from .base import Loader, register

RELEASES = "https://en-word.net/downloads"


@register
class OewnLoader(Loader):
    source_id = "oewn"
    ref = "2025"

    @property
    def filename(self) -> str:
        return f"english-wordnet-{self.ref}.xml.gz"

    def download(self, folder: Path) -> None:
        url = f"{RELEASES}/{self.filename}"
        download(url, folder / self.filename)
        write_source_info(folder, source=self.source_id, url=url, ref=self.ref, files=[self.filename])

    def read(self, folder, writer):
        sense_entry: dict[str, str] = {}
        pending: list[tuple[str, str, str]] = []  # (from entry, target sense, relation type)
        first_lemma: dict[str, str] = {}

        with gzip.open(folder / self.filename, "rb") as handle:
            entry_id = lemma = None
            for event, element in ET.iterparse(handle, events=("start", "end")):
                tag = element.tag
                if event == "start":
                    if tag == "LexicalEntry":
                        entry_id, lemma = element.get("id"), None
                    continue
                if tag == "Lemma":
                    lemma = element.get("writtenForm")
                    entry = self.node(f"entry/{entry_id}")
                    writer.form(entry, ENGLISH, lemma or "")
                    writer.prop(entry, "pos", element.get("partOfSpeech"))
                elif tag == "Sense":
                    synset = element.get("synset")
                    sense_entry[element.get("id")] = entry_id
                    writer.relation(self.node(f"entry/{entry_id}"), self.node(synset), "sense_of")
                    first_lemma.setdefault(synset, lemma)
                    for rel in element.findall("SenseRelation"):
                        pending.append((entry_id, rel.get("target"), rel.get("relType")))
                elif tag == "Synset":
                    synset = self.node(element.get("id"))
                    writer.concept(synset, "sense", first_lemma.get(element.get("id")))
                    writer.prop(synset, "pos", element.get("partOfSpeech"))
                    ili = element.get("ili")
                    writer.prop(synset, "ili", ili if ili and ili != "in" else None)
                    definition = element.find("Definition")
                    writer.prop(synset, "definition", definition.text if definition is not None else None)
                    for rel in element.findall("SynsetRelation"):
                        writer.relation(synset, self.node(rel.get("target")), rel.get("relType"))
                    element.clear()
                elif tag == "LexicalEntry":
                    element.clear()

        for from_entry, target_sense, rel_type in pending:
            to_entry = sense_entry.get(target_sense)
            if to_entry and rel_type:
                writer.relation(self.node(f"entry/{from_entry}"), self.node(f"entry/{to_entry}"), rel_type)
