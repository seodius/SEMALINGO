"""Tiny stand-ins for the real datasets, with the same table layouts and column names."""

from __future__ import annotations

import csv
import gzip
import io
import json
import zipfile
from pathlib import Path

from semalingo.raw import write_checksums

TERMS = "http://cldf.clld.org/v1.0/terms.rdf#"


def table_spec(url: str, columns: list[str], component: str | None = None, separators: dict | None = None) -> dict:
    separators = separators or {}
    spec = {
        "url": url,
        "tableSchema": {"columns": [{"name": c, **({"separator": separators[c]} if c in separators else {})} for c in columns]},
    }
    if component:
        spec["dc:conformsTo"] = TERMS + component
    return spec


def write_csv(path: Path, columns: list[str], rows: list[dict], zipped: bool = False) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)
    if zipped:
        with zipfile.ZipFile(str(path) + ".zip", "w") as archive:
            archive.writestr(path.name, buffer.getvalue())
    else:
        path.write_text(buffer.getvalue(), encoding="utf-8")


def write_cldf(folder: Path, metadata_name: str, tables: list[tuple[dict, list[dict], bool]]) -> None:
    """tables: (spec, rows, zipped)."""
    folder.mkdir(parents=True, exist_ok=True)
    metadata = {"dc:conformsTo": TERMS + "Wordlist", "tables": [spec for spec, _, _ in tables]}
    (folder / metadata_name).write_text(json.dumps(metadata), encoding="utf-8")
    for spec, rows, zipped in tables:
        columns = [c["name"] for c in spec["tableSchema"]["columns"]]
        write_csv(folder / spec["url"], columns, rows, zipped)


def concepticon(folder: Path) -> None:
    write_cldf(folder, "Wordlist-metadata.json", [
        (table_spec("concepticon.csv", ["ID", "Name", "Description", "ColumnSpec", "Semantic_Field", "Ontological_Category", "Replacement_ID"], "ParameterTable"), [
            {"ID": "0", "Name": "<NA>", "Description": "not yet mapped"},
            {"ID": "1209", "Name": "EYE", "Description": "The organ of sight.", "Semantic_Field": "The body", "Ontological_Category": "Person/Thing"},
            {"ID": "1409", "Name": "SEE", "Description": "To perceive with the eyes.", "Semantic_Field": "Sense perception", "Ontological_Category": "Action/Process"},
            {"ID": "1819", "Name": "LOOK", "Semantic_Field": "Sense perception", "Ontological_Category": "Action/Process"},
        ], False),
        (table_spec("conceptlists.csv", ["ID", "Name", "Tags", "Year", "Number_Of_Items"], "ContributionTable", {"Tags": "; "}), [
            {"ID": "Goddard-2011-63", "Name": "Goddard 2011", "Tags": "primes; nsm", "Year": "2011", "Number_Of_Items": "63"},
            {"ID": "Ogden-1930-200", "Name": "Ogden 1930", "Tags": "", "Year": "1930", "Number_Of_Items": "200"},
        ], False),
        (table_spec("concepts.csv", ["ID", "Name", "Number", "Index", "Conceptlist_ID", "Concepticon_ID", "Attributes"]), [
            {"ID": "Goddard-2011-63-1", "Name": "SEE", "Conceptlist_ID": "Goddard-2011-63", "Concepticon_ID": "1409"},
            {"ID": "Ogden-1930-200-1", "Name": "eye", "Conceptlist_ID": "Ogden-1930-200", "Concepticon_ID": "1209"},
            {"ID": "Ogden-1930-200-2", "Name": "unmapped", "Conceptlist_ID": "Ogden-1930-200", "Concepticon_ID": ""},
        ], False),
        (table_spec("parameter_network.csv", ["ID", "Description", "Target_Parameter_ID", "Source_Parameter_ID", "Edge_Is_Directed", "Contribution_ID", "relation", "data"], "ParameterNetwork"), [
            {"ID": "1409-narrower-1819", "Description": "narrower", "Target_Parameter_ID": "1819", "Source_Parameter_ID": "1409", "relation": "narrower"},
            {"ID": "a", "Description": "linked", "Target_Parameter_ID": "1409", "Source_Parameter_ID": "1209", "relation": "linked", "Contribution_ID": "X"},
            {"ID": "b", "Description": "linked", "Target_Parameter_ID": "1409", "Source_Parameter_ID": "1209", "relation": "linked", "Contribution_ID": "Y"},
        ], False),
    ])


def wold(folder: Path) -> None:
    write_cldf(folder, "cldf-metadata.json", [
        (table_spec("parameters.csv", ["ID", "Name", "Concepticon_ID", "Concepticon_Gloss", "Core_list", "Semantic_category", "Semantic_field", "Borrowed_score", "Age_score", "Simplicity_score"], "ParameterTable"), [
            {"ID": "4-21", "Name": "the eye", "Concepticon_ID": "1209", "Core_list": "yes", "Semantic_field": "The body", "Borrowed_score": "0.03", "Age_score": "0.95", "Simplicity_score": "1.0"},
            {"ID": "15-21", "Name": "to see", "Concepticon_ID": "1409", "Borrowed_score": "0.05"},
        ], False),
        (table_spec("languages.csv", ["ID", "Name", "Glottocode", "ISO639P3code"], "LanguageTable"), [
            {"ID": "13", "Name": "Dutch", "Glottocode": "dutc1256", "ISO639P3code": "nld"},
        ], False),
        (table_spec("forms.csv", ["ID", "Language_ID", "Parameter_ID", "Value", "Form", "Borrowed", "Borrowed_score"], "FormTable"), [
            {"ID": "13-4-21-1", "Language_ID": "13", "Parameter_ID": "4-21", "Value": "oog", "Form": "oog", "Borrowed": "5. no evidence for borrowing", "Borrowed_score": "0"},
            {"ID": "13-15-21-1", "Language_ID": "13", "Parameter_ID": "15-21", "Value": "zien", "Form": "zien", "Borrowed_score": "0"},
            {"ID": "13-15-21-2", "Language_ID": "13", "Parameter_ID": "15-21", "Value": "", "Form": ""},
        ], True),
    ])


def clics(folder: Path) -> None:
    write_cldf(folder, "StructureDataset-metadata.json", [
        (table_spec("concepts.csv", ["ID", "Name", "Concepticon_ID", "Concepticon_Gloss", "Family_Count", "Language_Count", "Community"]), [
            {"ID": "eye", "Concepticon_ID": "1209", "Concepticon_Gloss": "EYE", "Family_Count": "240", "Language_Count": "2100", "Community": "7"},
            {"ID": "see", "Concepticon_ID": "1409", "Concepticon_Gloss": "SEE", "Family_Count": "200", "Language_Count": "1900", "Community": "7"},
            {"ID": "know", "Concepticon_ID": "1410", "Concepticon_Gloss": "KNOW", "Family_Count": "150", "Language_Count": "1500", "Community": "9"},
        ], True),
        (table_spec("colexifications.csv", ["ID", "Name", "Source_Concept", "Target_Concept", "Family_Count", "Language_Count"], "ParameterTable"), [
            {"ID": "1", "Name": "SEE/KNOW", "Source_Concept": "SEE", "Target_Concept": "KNOW", "Family_Count": "12", "Language_Count": "40"},
            {"ID": "2", "Name": "EYE/SEED", "Source_Concept": "EYE", "Target_Concept": "SEED", "Family_Count": "3", "Language_Count": "5"},
        ], True),
    ])


def datsemshift(folder: Path) -> None:
    targets = [{"ID": "know", "NAME": "know", "Polysemy": 3, "Derivation": 1, "PolysemyByFamily": 2, "DerivationByFamily": 0}]
    write_cldf(folder, "cldf-metadata.json", [
        (table_spec("parameters.csv", ["ID", "Name", "Concepticon_ID", "Concepticon_Gloss", "Linked_Concepts", "Target_Concepts", "Definition", "Domain"], "ParameterTable"), [
            {"ID": "see", "Name": "see", "Concepticon_ID": "1409", "Linked_Concepts": "[]", "Target_Concepts": json.dumps(targets), "Domain": "Perception"},
            {"ID": "know", "Name": "know", "Concepticon_ID": "1410", "Linked_Concepts": "[]", "Target_Concepts": "[]", "Domain": "N/a"},
        ], False),
    ])


def glottolog(folder: Path) -> None:
    columns = ["ID", "Name", "Macroarea", "Latitude", "Longitude", "Glottocode", "ISO639P3code", "Level", "Family_ID", "Language_ID"]
    write_cldf(folder, "cldf-metadata.json", [
        (table_spec("languages.csv", columns, "LanguageTable"), [
            {"ID": "indo1319", "Name": "Indo-European", "Glottocode": "indo1319", "Level": "family"},
            {"ID": "dutc1256", "Name": "Dutch", "Macroarea": "Eurasia", "Latitude": "52.0", "Longitude": "5.0", "Glottocode": "dutc1256", "ISO639P3code": "nld", "Level": "language", "Family_ID": "indo1319"},
            {"ID": "zeeu1238", "Name": "Zeeuws", "Glottocode": "zeeu1238", "Level": "dialect", "Family_ID": "indo1319", "Language_ID": "dutc1256"},
        ], False),
    ])


def xlsx(path: Path, header: list[str], rows: list[list]) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def subtlex_nl(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    xlsx(folder / "SUBTLEX-NL with pos and Zipf.xlsx",
         ["Word", "FREQcount", "CDcount", "FREQlow", "CDlow", "FREQlemma", "SUBTLEXWF", "Zipf", "SUBTLEXCD", "Lg10CD", "dominant.pos", "dominant.pos.freq", "dominant.pos.lemma"],
         [["ik", 1744062, 8054, 778704, 3125, 1744527, 39883.0, "=LOG10((B2+1)/44.106)+3", 99.8, 3.9, "VNW", 1743609, "ik"],
          ["oog", 12000, 2500, 9000, 2000, 15000, 274.0, None, 30.9, 3.4, "N", 11900, "oog"],
          ["!", 50, 10, 50, 10, 50, 1.1, None, 0.1, 1.0, "LET", 50, "!"],
          [2009, 40, 9, 40, 9, 40, 0.9, None, 0.1, 1.0, "TW", 40, "2009"]])


def subtlex_uk(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    xlsx(folder / "SUBTLEX-UK_all.xlsx",
         ["Spelling", "Freq", "CapitFreq", "CD", "CDCount", "DomPoS", "DomPosFreq", "DomLemmaPos"],
         [["the", 9418422, 946828, 0.98, 44361, "determiner", 9412235, "the-determiner"],
          ["eye", 30000, 500, 0.2, 9000, "noun", 29000, "eye-noun"]])


def childlex(folder: Path) -> None:
    import sqlite3

    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "childlex")
    conn.executescript(
        "CREATE TABLE w(w TEXT, lw, f); CREATE TABLE l(l TEXT, ll, f); CREATE TABLE lex(w TEXT, p TEXT, l TEXT, f INT);"
        "INSERT INTO w VALUES ('Auge','auge',900),('Augen','augen',700),('!','!',82337);"
        "INSERT INTO l VALUES ('Auge','auge',1600),('!','!',82337);"
        "INSERT INTO lex VALUES ('Auge','NN','Auge',900),('Augen','NN','Auge',700),('!','$.','!',82337);"
    )
    conn.commit()
    conn.close()


def subtlex_us(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SUBTLEXus74286wordstextversion.tsv").write_text(
        "Word\tFREQcount\tCDcount\tFREQlow\tCdlow\tSUBTLWF\tLg10WF\tSUBTLCD\tLg10CD\n"
        "the\t1501908\t8388\t1339811\t8388\t29449.18\t6.1766\t100\t3.9237\n"
        "eye\t12000\t3000\t11000\t2900\t235.3\t4.08\t35.8\t3.48\n",
        encoding="utf-8",
    )


OEWN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LexicalResource>
  <Lexicon id="oewn" label="Open English WordNet" language="en" version="2025">
    <LexicalEntry id="oewn-eye-n">
      <Lemma writtenForm="eye" partOfSpeech="n"/>
      <Sense id="oewn-eye__1.08.00" synset="oewn-05317205-n"/>
    </LexicalEntry>
    <LexicalEntry id="oewn-see-v">
      <Lemma writtenForm="see" partOfSpeech="v"/>
      <Sense id="oewn-see__2.39.00" synset="oewn-02134765-v">
        <SenseRelation relType="derivation" target="oewn-sight__1.09.00"/>
      </Sense>
    </LexicalEntry>
    <LexicalEntry id="oewn-sight-n">
      <Lemma writtenForm="sight" partOfSpeech="n"/>
      <Sense id="oewn-sight__1.09.00" synset="oewn-05661902-n"/>
    </LexicalEntry>
    <Synset id="oewn-05317205-n" ili="i68829" partOfSpeech="n">
      <Definition>the organ of sight</Definition>
      <SynsetRelation relType="hypernym" target="oewn-05316100-n"/>
    </Synset>
    <Synset id="oewn-02134765-v" ili="i30587" partOfSpeech="v">
      <Definition>perceive by sight</Definition>
    </Synset>
    <Synset id="oewn-05661902-n" ili="in" partOfSpeech="n">
      <Definition>the ability to see</Definition>
    </Synset>
  </Lexicon>
</LexicalResource>
"""


def oewn(folder: Path, ref: str = "2025") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f"english-wordnet-{ref}.xml.gz", "wt", encoding="utf-8") as handle:
        handle.write(OEWN_XML)


BUILDERS = {"subtlex-nl": subtlex_nl, "subtlex-uk": subtlex_uk, "childlex": childlex, "subtlex-us": subtlex_us, "glottolog": glottolog, "concepticon": concepticon, "wold": wold, "clics": clics, "datsemshift": datsemshift, "oewn": oewn}


def install(raw_root: Path, source_id: str, ref: str) -> Path:
    """Put a fixture where a fetch would have put the real data, with checksums."""
    folder = raw_root / source_id / ref
    BUILDERS[source_id](folder)
    write_checksums(folder)
    return folder
