"""Step 4: WordNet proposals for Concepticon, the review queue, reviewed mappings and checks."""

import tempfile
import unittest
from pathlib import Path

from semalingo.linking import concepticon_gloss_labels, link, spellings
from semalingo.review import (
    check,
    decisions_to_rows,
    load_reviewed,
    read_review_files,
    read_unmatched,
    review_queue,
    write_review_file,
    write_unmatched_file,
)

from tests.test_loaders import LoaderTestCase


class LabelsTest(unittest.TestCase):
    def test_concepticon_gloss_labels(self):
        self.assertEqual(concepticon_gloss_labels("RAINING OR RAIN"), ["raining", "rain"])
        self.assertEqual(concepticon_gloss_labels("TEAR (OF EYE)"), ["tear"])
        self.assertEqual(spellings("door knocker"), ["door knocker", "doorknocker", "door-knocker"])


class MappingLayerTest(LoaderTestCase):
    def setUp(self):
        super().setUp()
        self.load("concepticon")
        self.load("oewn")

    def test_link_proposes_synsets_by_label_category_and_definition(self):
        result = link(self.conn)
        self.assertEqual(result["linked"], 2)  # EYE and SEE; WordNet has no "look" here
        rows = dict(self.rows("SELECT from_id, to_id FROM mappings WHERE method = 'gloss' AND from_id LIKE 'concepticon:%'"))
        self.assertEqual(rows["concepticon:1209"], "oewn:oewn-05317205-n")
        self.assertEqual(rows["concepticon:1409"], "oewn:oewn-02134765-v")
        self.assertEqual(link(self.conn), result)  # linking again replaces the proposals

    def test_review_queue_follows_list_order(self):
        link(self.conn)
        queue = review_queue(self.conn, ["Goddard-2011-63", "Ogden-1930-200"])
        self.assertEqual([item["gloss"] for item in queue], ["SEE", "EYE"])
        eye = queue[1]
        self.assertEqual(eye["lists"], ["Ogden-1930-200"])
        self.assertEqual(eye["candidates"][0]["lemmas"], ["eye"])
        self.assertEqual(eye["candidates"][0]["definition"], "the organ of sight")

    def test_reviewed_decisions_become_manual_mappings(self):
        link(self.conn)
        decisions = [
            {"concept": "concepticon:1209", "synset": "oewn:oewn-05317205-n", "type": "exact", "owner": True, "at": "2026-10-11T10:00:00Z"},
            {"concept": "concepticon:1819", "synset": None, "type": "none", "owner": False, "by": "u_someone", "note": "no synset"},
        ]
        edges, unmatched = decisions_to_rows(decisions, "seodius")
        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["reviewer"], "seodius")
        self.assertEqual(unmatched[0]["reviewer"], "u_someone")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "concepticon__oewn.tsv"
            write_review_file(path, edges)
            write_unmatched_file(Path(tmp) / "concepticon__oewn.unmatched.tsv", unmatched)
            self.assertEqual(read_review_files([path])[0]["method"], "manual")
            self.assertEqual(load_reviewed(self.conn, [path]), 1)
            self.assertEqual(load_reviewed(self.conn, [path]), 1)  # loading again replaces, never duplicates
            unmatched_ids = read_unmatched([Path(tmp) / "concepticon__oewn.unmatched.tsv"])
        self.assertEqual(
            self.rows("SELECT to_id, mapping_type, reviewer FROM mappings WHERE method = 'manual'"),
            [("oewn:oewn-05317205-n", "exact", "seodius")],
        )
        report = "\n".join(check(self.conn, ["Goddard-2011-63", "Ogden-1930-200"], unmatched=unmatched_ids))
        self.assertIn("reviewed: 1 linked, 1 with no WordNet equivalent", report)
        self.assertIn("Ogden-1930-200: 1 concept sets, 1 reviewed", report)

    def test_a_reviewed_row_needs_a_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x__y.tsv"
            write_review_file(path, [{"from_id": "a:1", "to_id": "b:2", "mapping_type": "exact", "method": "manual"}])
            with self.assertRaises(ValueError):
                read_review_files([path])


if __name__ == "__main__":
    unittest.main()


class ContextTest(LoaderTestCase):
    def setUp(self):
        super().setUp()
        for source in ("concepticon", "oewn", "sumo"):
            self.load(source)

    def test_sumo_hierarchy_facts_and_rule_mentions(self):
        from semalingo.context import sumo_context

        sumo = sumo_context(self.conn, ["Eye", "Seeing"])
        self.assertEqual(sumo["Eye"]["p"], ["Organ"])
        self.assertEqual(sumo["Organ"]["p"], ["AnimalAnatomicalStructure"])  # ancestors come along
        self.assertIn("AnimalAnatomicalStructure", sumo)
        self.assertEqual(sumo["Eye"]["d"], 'The Organ of sight; see "Seeing".')
        self.assertIn(["partition", "Organ", 1], sumo["Eye"]["f"])
        self.assertIn(["relatedInternalConcept", "Looking", 1], sumo["Seeing"]["f"])
        self.assertEqual(sumo["Eye"]["m"], [["Organ", 1]])
        self.assertNotIn("f", sumo["Organ"])  # facts only for the terms asked for

    def test_wordnet_hierarchy_and_concepticon_relations(self):
        from semalingo.context import concept_relations, wordnet_context

        synset = self.value("SELECT from_id FROM relations WHERE source_id = 'oewn' AND relation_type = 'hypernym' LIMIT 1")
        parent = self.value("SELECT to_id FROM relations WHERE source_id = 'oewn' AND relation_type = 'hypernym' AND from_id = ?", synset)
        wordnet = wordnet_context(self.conn, [synset])
        self.assertEqual(wordnet[synset]["p"], [parent])
        self.assertIn(parent, wordnet)
        self.assertTrue(wordnet[parent]["l"])
        self.assertEqual(concept_relations(self.conn, ["concepticon:1409"]), {"concepticon:1409": [["narrower", "concepticon:1819", "LOOK"]]})
