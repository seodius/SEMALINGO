"""How languages express a concept set: list words, Lexibank forms, colexifications, spread."""

import unittest

from semalingo.review import review_payload
from semalingo.usage import _distinct, _word, concept_usage

from tests.test_loaders import LoaderTestCase

EYE, SEE = "concepticon:1209", "concepticon:1409"


class WordsTest(unittest.TestCase):
    def test_list_glosses_lose_notes_and_asterisks(self):
        self.assertEqual(_word(" 木头 [B = 木材] "), "木头")
        self.assertEqual(_word("大*"), "大")
        self.assertEqual(_word("*big"), "big")
        self.assertEqual(_word("lang (tijd)"), "lang (tijd)")

    def test_spelling_variants_and_romanizations_are_dropped(self):
        self.assertEqual(_distinct(["árbol", "Arbol", "árboles"]), ["árbol", "árboles"])
        self.assertEqual(_distinct(["дерево", "Diereva"]), ["дерево"])
        self.assertEqual(_distinct(["Diereva"]), ["Diereva"])  # the only word there is


class ConceptUsageTest(LoaderTestCase):
    def setUp(self):
        super().setUp()
        for source in ("concepticon", "glottolog", "lexibank", "clics", "subtlex-nl"):
            self.load(source)

    def test_words_forms_spread_and_colexifications(self):
        usage = concept_usage(self.conn, [EYE, SEE])
        self.assertEqual(usage["languages"]["dutc1256"], {"name": "Dutch", "family": "Indo-European"})
        self.assertEqual(usage["languages"]["stan1293"], {"name": "stan1293", "family": ""})  # not in this Glottolog
        eye = usage["concepts"][EYE]
        self.assertEqual(eye["words"]["dutc1256"][0]["w"], "oog")
        zipf = self.value("SELECT p.value_num FROM properties p JOIN forms f ON f.form_id = p.node_id "
                          "WHERE f.source_id = 'subtlex-nl' AND f.written_form = 'oog' AND p.property = 'zipf'")
        self.assertEqual(eye["words"]["dutc1256"][0]["z"], zipf)  # from SUBTLEX-NL
        self.assertEqual(eye["words"]["stan1293"], [{"w": "eye"}])
        self.assertEqual(eye["forms"]["dutc1256"], [{"f": "oːx", "n": 1}])
        self.assertEqual(eye["spread"], {"varieties": 1, "languages": 1, "families": 1})
        see = usage["concepts"][SEE]
        self.assertEqual(see["colexified"], [{"c": "concepticon:1410", "g": "concepticon:1410", "fam": 12}])
        self.assertEqual(see["spread"], {})  # no Lexibank form

    def test_one_form_for_two_concept_sets_in_one_list(self):
        form = "lexibank:form/wold-Dutch-tear-2"
        self.conn.execute("INSERT INTO forms VALUES (?, 'lexibank', 'dutc1256', 'oːx')", [form])
        self.conn.executemany(
            "INSERT INTO relations VALUES ('lexibank', ?, ?, ?, NULL)",
            [(form, "lexibank:tear", "expresses"), (form, "lexibank:variety/wold-Dutch", "in_list")],
        )
        self.conn.execute("INSERT INTO properties VALUES (?, 'lexibank', 'segments', NULL, 'oː x')", [form])
        eye = concept_usage(self.conn, [EYE])["concepts"][EYE]
        self.assertEqual(eye["shared"]["dutc1256"], [{"f": "oːx", "also": ["concepticon:1414"]}])
        self.assertEqual(eye["forms"]["dutc1256"], [{"f": "oːx", "n": 1}])

    def test_review_payload_carries_usage(self):
        payload = review_payload(self.conn, ["Ogden-1930-200"])
        self.assertEqual([item["gloss"] for item in payload["items"]], ["EYE"])
        self.assertIn("dutc1256", payload["items"][0]["usage"]["words"])
        self.assertIn("dutc1256", payload["languages"])
