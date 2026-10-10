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
        (table_spec("languages.csv", ["ID", "Name", "Macroarea", "Latitude", "Longitude", "Glottocode", "ISO639P3code"], "LanguageTable"), [
            {"ID": "english", "Name": "English", "Glottocode": "stan1293"},
            {"ID": "dutch", "Name": "Dutch", "Glottocode": "dutc1256"},
            {"ID": "protoworld", "Name": "protoworld"},
        ], False),
        (table_spec("glosses.csv", ["ID", "Language_ID", "Parameter_ID", "Form", "Source", "Concept_ID"], "FormTable", {"Source": ";"}), [
            {"ID": "Ogden-1930-200-1-1", "Language_ID": "english", "Parameter_ID": "1209", "Form": "eye", "Concept_ID": "Ogden-1930-200-1"},
            {"ID": "Ogden-1930-200-1-2", "Language_ID": "dutch", "Parameter_ID": "1209", "Form": "oog ", "Concept_ID": "Ogden-1930-200-1"},
            {"ID": "Ogden-1930-200-2-1", "Language_ID": "english", "Parameter_ID": "", "Form": "unmapped", "Concept_ID": "Ogden-1930-200-2"},
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


def norare(folder: Path) -> None:
    aoa = json.dumps({"datatype": {"base": "decimal", "minimum": 1, "maximum": 25}, "name": "ENGLISH_AOA_MEAN"})
    label = json.dumps({"datatype": "string", "name": "ENGLISH_PERCEPTUAL_DOMINANT"})
    visual = json.dumps({"datatype": "decimal", "name": "DUTCH_VISUAL_MEAN"})
    write_cldf(folder, "Wordlist-metadata.json", [
        (table_spec("glosses.csv", ["ID", "Language_ID", "Parameter_ID", "Form", "Segments", "Comment", "Source", "Dataset_ID"], "FormTable", {"Source": ";"}), [
            {"ID": "Kuperman-2012-AoA-stan1293-1", "Language_ID": "eng", "Parameter_ID": "1209", "Form": "eye", "Dataset_ID": "Kuperman-2012-AoA"},
            {"ID": "Kuperman-2012-AoA-stan1293-2", "Language_ID": "eng", "Parameter_ID": "1409", "Form": "see", "Dataset_ID": "Kuperman-2012-AoA"},
            {"ID": "Speed-2021-Sensorimotor-dutc1256-1", "Language_ID": "nld", "Parameter_ID": "1209", "Form": "oog", "Dataset_ID": "Speed-2021-Sensorimotor"},
        ], False),
        (table_spec("concepticon.csv", ["ID", "Name", "Description", "ColumnSpec", "Concepticon_ID", "glosses", "count_datasets", "count_variables"], "ParameterTable"), [
            {"ID": "1209", "Name": "EYE", "Concepticon_ID": "1209", "count_datasets": "40", "count_variables": "200"},
            {"ID": "1409", "Name": "SEE", "Concepticon_ID": "1409", "count_datasets": "30", "count_variables": "150"},
        ], False),
        (table_spec("datasets.csv", ["ID", "Name", "Description", "Contributor", "Citation", "Year", "Source", "URL", "Alias"], "ContributionTable", {"Source": ";"}), [
            {"ID": "Kuperman-2012-AoA", "Name": "Kuperman 2012 AoA", "Year": "2012", "Citation": "Kuperman et al. 2012", "URL": "https://doi.org/10.3758/s13428-012-0210-4"},
            {"ID": "Speed-2021-Sensorimotor", "Name": "Speed 2021 Sensorimotor", "Year": "2021"},
        ], False),
        (table_spec("languages.csv", ["ID", "Name", "Macroarea", "Latitude", "Longitude", "Glottocode", "ISO639P3code"], "LanguageTable"), [
            {"ID": "eng", "Name": "English", "Glottocode": "stan1293"},
            {"ID": "nld", "Name": "Dutch", "Glottocode": "dutc1256"},
        ], False),
        (table_spec("variables.csv", ["ID", "Dataset_ID", "Language_ID", "Name", "Note", "Other", "Source", "Category", "Type", "Method", "Result", "Datatype"]), [
            {"ID": "Kuperman-2012-AoA-ENGLISH_AOA_MEAN", "Dataset_ID": "Kuperman-2012-AoA", "Language_ID": "eng", "Note": "Mean AoA rating.", "Category": "ratings", "Type": "mean", "Method": "users", "Result": "AoA", "Datatype": aoa},
            {"ID": "Kuperman-2012-AoA-ENGLISH_PERCEPTUAL_DOMINANT", "Dataset_ID": "Kuperman-2012-AoA", "Language_ID": "eng", "Other": "dominant", "Category": "ratings", "Type": "linguistic", "Method": "users", "Result": "sensory modality", "Datatype": label},
            {"ID": "Speed-2021-Sensorimotor-DUTCH_VISUAL_MEAN", "Dataset_ID": "Speed-2021-Sensorimotor", "Language_ID": "nld", "Other": "visual", "Category": "ratings", "Type": "mean", "Method": "users", "Result": "sensory modality", "Datatype": visual},
        ], False),
        (table_spec("norare.csv", ["ID", "Unit_ID", "Variable_ID", "Value"]), [
            {"ID": "1", "Unit_ID": "Kuperman-2012-AoA-stan1293-1", "Variable_ID": "Kuperman-2012-AoA-ENGLISH_AOA_MEAN", "Value": "3.6"},
            {"ID": "2", "Unit_ID": "Kuperman-2012-AoA-stan1293-2", "Variable_ID": "Kuperman-2012-AoA-ENGLISH_AOA_MEAN", "Value": "3.1"},
            {"ID": "3", "Unit_ID": "Kuperman-2012-AoA-stan1293-1", "Variable_ID": "Kuperman-2012-AoA-ENGLISH_PERCEPTUAL_DOMINANT", "Value": "Visual"},
            {"ID": "4", "Unit_ID": "Speed-2021-Sensorimotor-dutc1256-1", "Variable_ID": "Speed-2021-Sensorimotor-DUTCH_VISUAL_MEAN", "Value": "0"},
        ], True),
    ])


def concepticon_maps(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    english = [
        ("1209", "EYE///eye", 10), ("1209", "EYE///the eye", 3), ("1209", "EYE///the eyes", 3),
        ("1409", "SEE///to see", 8), ("1409", "SEE///see (perceive)", 2),
        ("1650", "WATCH///to watch", 4), ("1650", "WATCH///watch", 1), ("3349", "WRISTWATCH///watch", 2),
        ("0", "UNLINKED///nothing", 1),
    ]
    dutch = [("1209", "EYE///oog", 2), ("1409", "SEE///zien, kijken", 1)]
    for name, rows in (("map-en.tsv", english), ("map-nl.tsv", dutch)):
        lines = ["ID\tGLOSS\tPRIORITY"] + [f"{i}\t{g}\t{p}" for i, g, p in rows]
        (folder / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def wiki_page(source_id: str):
    from tests.wiki_pages import WIKI_PAGES

    def build(folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "page.wikitext").write_text(WIKI_PAGES[source_id], encoding="utf-8")
    return build


def sumo(folder: Path) -> None:
    from tests.sumo_files import MERGE_KIF, WORDNET_NOUN

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "Merge.kif").write_text(MERGE_KIF, encoding="utf-8")
    (folder / "WordNetMappings30-noun.txt").write_text(WORDNET_NOUN, encoding="utf-8")


def cili(folder: Path) -> None:
    from tests.sumo_files import CILI_MAP

    folder.mkdir(parents=True, exist_ok=True)
    (folder / "ili-map-pwn30.tab").write_text(CILI_MAP, encoding="utf-8")


def kuperman_aoa(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rows = [
        "Word,Alternative.spelling,Freq_pm,Dom_PoS_SUBTLEX,Nletters,Nphon,Nsyll,Lemma_highest_PoS,AoA_Kup,Perc_known,AoA_Kup_lem,Perc_known_lem,AoA_Bird_lem,AoA_Bristol_lem,AoA_Cort_lem,AoA_Schock",
        "eye,eye,111.78,Noun,3,1,1,eye,3.75,1.00,3.75,1.00,4.14,3.58,3.33,",
        "eyes,eyes,221.55,Noun,4,2,1,eye,3.44,1.00,3.44,1.00,,,,",
        "abacuses,abacuses,0.02,Noun,8,9,4,abacus,NA,NA,8.69,0.65,,,,",
        "colour,color,40.0,Noun,6,4,2,colour,4.5,1.00,4.5,1.00,,,,",
    ]
    (folder / "en.aoa.csv").write_bytes(("\r\n".join(rows) + "\r\n").encode("utf-8"))


def brysbaert_concreteness(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rows = [
        "Word,Bigram,Conc.M,Conc.SD,Unknown,Total,Percent_known,SUBTLEX,Dom_Pos",
        "eye,0,4.9,0.41,0,29,1.0,5701,Noun",
        "unhappiness,0,1.52,0.78,0,29,1.0,59,Noun",
        "baking soda,1,5.0,0.0,0,27,1.0,0,0",
    ]
    (folder / "concreteness_ratings.csv").write_bytes(("\r\n".join(rows) + "\r\n").encode("utf-8"))


def lexibank(folder: Path) -> None:
    languages = (table_spec("languages.csv", ["ID", "Name", "Macroarea", "Latitude", "Longitude", "Glottocode", "ISO639P3code", "Family", "Dataset", "Incollections"], "LanguageTable"), [
        {"ID": "wold-Dutch", "Name": "Dutch", "Macroarea": "Eurasia", "Latitude": "52.0", "Longitude": "5.0", "Glottocode": "dutc1256", "Family": "Indo-European", "Dataset": "wold", "Incollections": "ClicsCore"},
        {"ID": "abvd-Tagalog", "Name": "Tagalog", "Glottocode": "taga1270", "Family": "Austronesian", "Dataset": "abvd"},
    ], False)
    write_cldf(folder, "wordlist-metadata.json", [
        (table_spec("forms.csv", ["ID", "Language_ID", "Parameter_ID", "Form", "Segments"], "FormTable", {"Segments": " "}), [
            {"ID": "wold-Dutch-eye-1", "Language_ID": "wold-Dutch", "Parameter_ID": "eye", "Form": "oːx", "Segments": "oː x"},
            {"ID": "wold-Dutch-tear-1", "Language_ID": "wold-Dutch", "Parameter_ID": "tear", "Form": "traːn", "Segments": "t r aː n"},
            {"ID": "abvd-Tagalog-tear-1", "Language_ID": "abvd-Tagalog", "Parameter_ID": "tear", "Form": "luha", "Segments": "l u h a"},
        ], True),
        (table_spec("concepts.csv", ["ID", "Name", "Concepticon_ID", "Concepticon_Gloss", "Central_Concept", "Core_Concept"], "ParameterTable"), [
            {"ID": "eye", "Name": "EYE", "Concepticon_ID": "1209", "Concepticon_Gloss": "EYE", "Central_Concept": "EYE", "Core_Concept": "Swadesh-1955-100"},
            {"ID": "tear", "Name": "TEAR (OF EYE)", "Concepticon_ID": "1414", "Concepticon_Gloss": "TEAR (OF EYE)"},
        ], False),
        languages,
    ])
    for part, rows in (
        ("lexicon", [("EyeInTear", "eye in tear", [("wold-Dutch", "False"), ("abvd-Tagalog", "?")])]),
        ("phonology", [("SyllableStructure", "syllable structure", [("wold-Dutch", "3"), ("abvd-Tagalog", "2")])]),
    ):
        features = [{"ID": fid, "Name": name, "Description": ""} for fid, name, _ in rows]
        values = [{"ID": f"{lang}-{fid}", "Language_ID": lang, "Parameter_ID": fid, "Value": value, "Code_ID": f"{fid}-{value}"}
                  for fid, _, pairs in rows for lang, value in pairs]
        codes = [{"ID": "EyeInTear-True", "Parameter_ID": "EyeInTear", "Name": "eye in tear"},
                 {"ID": "SyllableStructure-3", "Parameter_ID": "SyllableStructure", "Name": "complex syllable structure"}]
        write_cldf(folder, f"{part}-metadata.json", [
            (table_spec(f"{part}-values.csv", ["ID", "Language_ID", "Parameter_ID", "Value", "Code_ID"], "ValueTable"), values, False),
            (table_spec(f"{part}-features.csv", ["ID", "Name", "Description"], "ParameterTable"), features, False),
            (table_spec(f"{part}-codes.csv", ["ID", "Parameter_ID", "Name"], "CodeTable"), codes, False),
            languages,
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


BUILDERS = {"subtlex-nl": subtlex_nl, "subtlex-uk": subtlex_uk, "childlex": childlex, "subtlex-us": subtlex_us, "glottolog": glottolog, "concepticon": concepticon, "wold": wold, "clics": clics, "datsemshift": datsemshift, "oewn": oewn, "norare": norare, "concepticon-maps": concepticon_maps}
BUILDERS.update({"lexibank": lexibank, "sumo": sumo, "cili": cili, "kuperman-aoa": kuperman_aoa, "brysbaert-concreteness": brysbaert_concreteness})
BUILDERS.update({sid: wiki_page(sid) for sid in ("basic-english", "wiktionary-1000-basic", "basic-english-combined", "voa-special-english", "simple-misspellings", "nsm-primes")})


def install(raw_root: Path, source_id: str, ref: str) -> Path:
    """Put a fixture where a fetch would have put the real data, with checksums."""
    folder = raw_root / source_id / ref
    BUILDERS[source_id](folder)
    write_checksums(folder)
    return folder
