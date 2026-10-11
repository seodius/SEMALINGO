"""SUMO (Suggested Upper Merged Ontology) and the Collaborative Interlingual Index (CILI).

SUMO: every term in a subclass, instance, subrelation or subAttribute statement, or with an
English documentation string, becomes a concept "sumo:<Term>" (kind "class"), with relations
"subclass_of", "instance_of", "subrelation_of", "subattribute_of" and the properties
"documentation" and "term_format" (its English name). Only top-level statements count: a
subclass statement inside a rule is a condition, not a fact.

Other ground facts between two terms keep SUMO's own relation name as the relation type:
(disjoint Plant Animal), (relatedInternalConcept Seeing Looking), (typicalPart Feather Bird),
(contraryAttribute Prone Supine), (located Paris France), ... A decomposition of a class into
parts, (partition Organism Plant Animal ...), becomes one relation per part, from the part to
the class. Facts with more arguments, or with numbers or strings, are left out.

Most of what SUMO says about a term is in rules ((=> (instance ?E Eye) ...)). They are not
translated into logic here, but the classes a rule names are noted: "rule_mentions" links two
classes that appear in the same rule, weighted by the number of such rules (Eye and UpperEyelid,
Food and Eating). Functions (...Fn) are left out.

SUMO's WordNet mappings link terms to WordNet 3.0 synsets, written "pwn30:<offset>-<pos>".
They become imported mappings from the SUMO term: "=" (equivalent) is exact; "+" (the synset
is subsumed by the term) and "@" (the synset is an instance of the term) are narrower.
Complement mappings ("[", ":", "]": the synset is the opposite) are left out.

CILI: Open English WordNet has renumbered its synsets, so the WordNet 3.0 numbers that SUMO
(and NoRaRe's Bond-2013-OMW) use reach OEWN through the interlingual index: "cili:<ili>" is
exact to "pwn30:<offset>-<pos>", and OEWN synsets map to "cili:<ili>" themselves.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import ClassVar, Iterator
from urllib.parse import quote

from ..fetch import download, github_raw, write_source_info
from ..ids import make_node_id
from .base import Loader, register

TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|;[^\n]*|[()]|[^\s()";]+')
TERM = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
RELATIONS = {"subclass": "subclass_of", "instance": "instance_of", "subrelation": "subrelation_of", "subAttribute": "subattribute_of"}
# n-ary facts that split their first argument into the others
DECOMPOSITIONS = ("partition", "disjointDecomposition", "exhaustiveDecomposition", "exhaustiveAttribute")
# heads that are not relations between terms
NOT_FACTS = {"documentation", "termFormat", "format", "externalImage", "comment"}
LOGIC = {"=>", "<=>", "and", "or", "not", "exists", "forall"}


def atoms(form) -> Iterator[str]:
    for item in form:
        if isinstance(item, list):
            yield from atoms(item)
        else:
            yield item
MAPPING = re.compile(r"&%([A-Za-z0-9_-]+)([=+@\[\]:])")
MAPPING_TYPES = {"=": "exact", "+": "narrower", "@": "narrower"}
ENGLISH_NAMES = ("EnglishLanguage", "EnglishWrittenLanguage")
WORDNET_FILES = tuple(f"WordNetMappings30-{pos}.txt" for pos in ("noun", "verb", "adj", "adv"))


def top_level_forms(text: str) -> Iterator[list]:
    """The top-level lists of a SUO-KIF file, as nested Python lists of atoms and strings."""
    stack: list[list] = []
    for match in TOKEN.finditer(text):
        token = match.group(0)
        if token.startswith(";"):
            continue
        if token == "(":
            stack.append([])
        elif token == ")":
            if not stack:
                continue  # unbalanced closing bracket: skip it
            done = stack.pop()
            if stack:
                stack[-1].append(done)
            else:
                yield done
        elif stack:
            stack[-1].append(token)


def unquote(text: str) -> str:
    return " ".join(text[1:-1].replace('\\"', '"').replace("&%", "").split())


@register
class SumoLoader(Loader):
    source_id = "sumo"
    repo = "ontologyportal/sumo"
    commit: ClassVar[str] = "b9934d3bbdf2931dd4635c3ddd6aba37110c71de"
    ref = "b9934d3"
    # all ontology files at this commit except the small test ontologies (tiny*.kif)
    kif_files: ClassVar[tuple[str, ...]] = (
        "Anatomy.kif", "Animals.kif", "ArabicCulture.kif", "Astronomy.kif", "Biography.kif", "CCTrep.kif",
        "Cars.kif", "Catalog.kif", "Cellular&TelephoneArchitecture.kif", "ClimateStatecraft.kif",
        "Communications.kif", "ComputerInput.kif", "ComputingBrands.kif", "CountriesAndRegions.kif",
        "DARPA_ARC.kif", "Dining.kif", "Economy.kif", "FOAFmap.kif", "Facebook.kif", "FinancialOntology.kif",
        "Food.kif", "GentleM.kif", "GeochronologicTimes.kif", "Geography.kif", "Government.kif",
        "GymEquipment.kif", "Hotel.kif", "HouseholdAppliances.kif", "Justice.kif", "Languages.kif", "Law.kif",
        "Media.kif", "Medicine.kif", "Merge.kif", "Mid-level-ontology.kif", "Military.kif",
        "MilitaryDevices.kif", "MilitaryPersons.kif", "MilitaryProcesses.kif", "ModSim.kif", "Muscles.kif",
        "Music.kif", "NameTermFormat.kif", "NavalModeling.kif", "Objects.kif", "People.kif", "QoSontology.kif",
        "Sports.kif", "TransnationalIssues.kif", "TransportDetail.kif", "Transportation.kif", "Trees.kif",
        "UXExperimentalTerms.kif", "VirusProteinAndCellPart.kif", "WMD.kif", "Weather.kif",
        "WeatherStatecraft.kif", "WorldAirports.kif", "arteries.kif", "capabilities.kif",
        "domainEnglishFormat.kif", "emotion.kif", "engineering.kif", "english_format.kif", "mondial.kif",
        "naics.kif", "nlg_supplement_formats.kif", "pictureList-ImageNet.kif", "pictureList.kif",
    )

    def download(self, folder: Path) -> None:
        files = []
        for name in self.kif_files:
            download(github_raw(self.repo, self.commit, quote(name)), folder / name)
            files.append(name)
        for name in WORDNET_FILES:
            download(github_raw(self.repo, self.commit, f"WordNetMappings/{name}"), folder / name)
            files.append(name)
        write_source_info(folder, source=self.source_id, repo=self.repo, ref=self.ref, commit=self.commit, files=files)

    def read(self, folder, writer):
        terms: dict[str, str | None] = {}
        mentions: Counter = Counter()
        for name in self.kif_files:
            path = folder / name
            if not path.exists():
                continue
            for form in top_level_forms(path.read_text(encoding="utf-8", errors="replace")):
                if not form or not isinstance(form[0], str):
                    continue
                head = form[0]
                if head in LOGIC:
                    named = {a for a in atoms(form) if a[:1].isupper() and TERM.match(a) and not a.endswith("Fn")}
                    mentions.update((a, b) for a in named for b in named if a != b)
                    continue
                ground = len(form) >= 3 and all(isinstance(t, str) and TERM.match(t) for t in form[1:])
                if head in RELATIONS and len(form) == 3 and ground:
                    writer.relation(self.node(form[1]), self.node(form[2]), RELATIONS[head])
                    terms.setdefault(form[1], None)
                    terms.setdefault(form[2], None)
                elif head in DECOMPOSITIONS and ground:
                    for part in form[2:]:
                        writer.relation(self.node(part), self.node(form[1]), head)
                elif len(form) == 3 and ground and head not in NOT_FACTS and TERM.match(head):
                    writer.relation(self.node(form[1]), self.node(form[2]), head)
                elif head == "documentation" and len(form) == 4 and form[2] in ENGLISH_NAMES and isinstance(form[1], str) \
                        and TERM.match(form[1]) and isinstance(form[3], str) and form[3].startswith('"'):
                    writer.prop(self.node(form[1]), "documentation", unquote(form[3]))
                    terms.setdefault(form[1], None)
                elif head == "termFormat" and len(form) == 4 and form[1] in ENGLISH_NAMES and isinstance(form[2], str) \
                        and TERM.match(form[2]) and isinstance(form[3], str) and form[3].startswith('"'):
                    if terms.get(form[2]) is None:
                        terms[form[2]] = unquote(form[3])
                    writer.prop(self.node(form[2]), "term_format", terms[form[2]])
        for name in WORDNET_FILES:
            path = folder / name
            if not path.exists():
                continue
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if line.startswith(" ") or "|" not in line:
                        continue  # licence header lines start with spaces
                    fields = line.split(" ", 3)
                    synset = make_node_id("pwn30", f"{fields[0]}-{fields[2]}")
                    for term, symbol in MAPPING.findall(line.rsplit("|", 1)[1]):
                        if symbol in MAPPING_TYPES:
                            writer.mapping(self.node(term), synset, MAPPING_TYPES[symbol])
                            terms.setdefault(term, None)  # some mapped terms have no statement of their own

        for (a, b), n in mentions.items():
            writer.relation(self.node(a), self.node(b), "rule_mentions", float(n))
        for term, name in terms.items():
            writer.concept(self.node(term), "class", name or term)


@register
class CiliLoader(Loader):
    source_id = "cili"
    repo = "globalwordnet/cili"
    commit: ClassVar[str] = "a895d7ecb18019dda3443f98901e59d81ce8722b"
    ref = "a895d7e"
    filename: ClassVar[str] = "ili-map-pwn30.tab"

    def download(self, folder: Path) -> None:
        download(github_raw(self.repo, self.commit, self.filename), folder / self.filename)
        write_source_info(folder, source=self.source_id, repo=self.repo, ref=self.ref, commit=self.commit, files=[self.filename])

    def read(self, folder, writer):
        with open(folder / self.filename, encoding="utf-8") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) == 2 and parts[0].startswith("i"):
                    writer.mapping(self.node(parts[0]), make_node_id("pwn30", parts[1]), "exact")
