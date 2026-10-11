"""Custom concept lists: files, the review page's export, loading, and the review queue."""

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from semalingo.cli import cmd_export_review
from semalingo.linking import link
from semalingo.lists import list_ids, lists_from_page, load_lists, read_lists, slug, write_lists
from semalingo.review import review_queue

from tests.test_loaders import LoaderTestCase

LISTS = [{
    "id": "core",
    "name": "Core concepts",
    "description": "First words to coin",
    "created_by": "seodius",
    "created_at": "2026-10-11",
    "entries": [
        {"key": "1209", "concept": "concepticon:1209", "gloss": "EYE", "note": "body part", "added_by": "seodius", "added_at": "2026-10-11"},
        {"key": "see-on-purpose", "concept": "", "gloss": "SEE ON PURPOSE", "definition": "To see something because you choose to.",
         "category": "Action/Process", "closest": "concepticon:1409", "relation": "broader", "added_by": "seodius", "added_at": "2026-10-11"},
    ],
}]


def page_export(folder: Path) -> None:
    """What ArtifactData writes for the page's lists collection and one list's entries."""
    (folder / "lists" / "core" / "entries").mkdir(parents=True)
    (folder / "lists" / "core.json").write_text(json.dumps(
        {"id": "core", "name": "Core concepts", "description": "First words to coin", "by": "u_owner", "owner": True, "at": "2026-10-11T09:00:00Z"}))
    entries = {
        "1209": {"key": "1209", "concept": "concepticon:1209", "gloss": "EYE", "by": "u_friend", "owner": False, "at": "2026-10-11T09:01:00Z"},
        "see-on-purpose": {"key": "see-on-purpose", "concept": None, "gloss": "SEE ON PURPOSE", "definition": "To see something because you choose to.",
                           "category": "Action/Process", "closest": "concepticon:1409", "relation": "broader", "by": "u_owner", "owner": True,
                           "at": "2026-10-11T09:02:00Z"},
    }
    for key, body in entries.items():
        (folder / "lists" / "core" / "entries" / f"{key}.json").write_text(json.dumps({"id": key, "data": body, "version": 1}))


class ListFilesTest(unittest.TestCase):
    def test_slug(self):
        self.assertEqual(slug("Agent of (doer)"), "agent-of-doer")

    def test_write_and_read_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(write_lists(Path(tmp), LISTS), 2)
            lists = read_lists(Path(tmp))
            self.assertEqual([l["name"] for l in lists], ["Core concepts"])
            self.assertEqual([e["gloss"] for e in lists[0]["entries"]], ["EYE", "SEE ON PURPOSE"])
            self.assertEqual(list_ids(Path(tmp)), ["custom:list/core"])
        self.assertEqual(list_ids(Path("no/such/folder")), [])

    def test_an_entry_needs_a_concept_or_a_gloss(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_lists(Path(tmp), [{**LISTS[0], "entries": [{"key": "x", "note": "nothing"}]}])
            with self.assertRaises(ValueError):
                read_lists(Path(tmp))

    def test_lists_from_the_review_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            page_export(Path(tmp))
            lists = lists_from_page(Path(tmp), "seodius")
        self.assertEqual(lists[0]["created_by"], "seodius")
        entries = {e["key"]: e for e in lists[0]["entries"]}
        self.assertEqual(entries["1209"]["added_by"], "u_friend")
        self.assertEqual(entries["see-on-purpose"]["added_by"], "seodius")
        self.assertEqual(entries["see-on-purpose"]["relation"], "broader")
        self.assertEqual(entries["see-on-purpose"]["added_at"], "2026-10-11")


class LoadListsTest(LoaderTestCase):
    def setUp(self):
        super().setUp()
        self.load("concepticon")
        self.load("oewn")
        self.folder = Path(self.tmp.name) / "lists"
        write_lists(self.folder, LISTS)

    def test_lists_become_list_nodes_with_entries(self):
        counts = load_lists(self.conn, self.folder)
        self.assertEqual(counts["concepts"], 2)  # the list and one new concept
        self.assertEqual(self.value("SELECT gloss FROM concepts WHERE concept_id = 'custom:list/core'"), "Core concepts")
        members = sorted(r[0] for r in self.rows("SELECT from_id FROM relations WHERE to_id = 'custom:list/core' AND relation_type = 'in_list'"))
        self.assertEqual(members, ["concepticon:1209", "custom:concept/see-on-purpose"])
        self.assertEqual(
            self.rows("SELECT to_id, mapping_type, method FROM mappings WHERE from_id = 'custom:concept/see-on-purpose'"),
            [("concepticon:1409", "broader", "imported")],
        )
        self.assertEqual(load_lists(self.conn, self.folder), counts)  # loading again replaces

    def test_review_queue_takes_custom_lists_and_new_concepts(self):
        load_lists(self.conn, self.folder)
        link(self.conn)
        queue = review_queue(self.conn, ["Ogden-1930-200", "custom:list/core"])
        self.assertEqual([item["gloss"] for item in queue], ["EYE", "SEE ON PURPOSE"])
        self.assertEqual(queue[0]["lists"], ["Ogden-1930-200", "custom:list/core"])
        new = queue[1]
        self.assertEqual(new["definition"], "To see something because you choose to.")
        self.assertEqual(new["candidates"][0]["synset"], "oewn:oewn-02134765-v")  # see, verb

    def test_decisions_on_new_concepts_stay_with_the_lists(self):
        decisions = Path(self.tmp.name) / "decisions"
        decisions.mkdir()
        for name, body in {
            "1209": {"concept": "concepticon:1209", "synset": "oewn:oewn-05317205-n", "type": "exact", "owner": True},
            "custom:concept~see-on-purpose": {"concept": "custom:concept/see-on-purpose", "synset": "oewn:oewn-02134765-v", "type": "narrower", "owner": True},
        }.items():
            (decisions / f"{name}.json").write_text(json.dumps(body))
        out = Path(self.tmp.name) / "mappings" / "concepticon__oewn.tsv"
        args = argparse.Namespace(folder=str(decisions), reviewer="seodius", out=str(out), custom_lists=str(self.folder))
        cmd_export_review(args)
        self.assertNotIn("custom:", out.read_text())
        self.assertIn("custom:concept/see-on-purpose", (self.folder / "custom__oewn.tsv").read_text())
