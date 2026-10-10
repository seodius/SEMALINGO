import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from semalingo import fetch
from semalingo.cldf import Dataset
from semalingo.db import apply_schema
from semalingo.loaders import LOADERS
from semalingo.raw import MANIFEST
from semalingo.registry import load_registry
from semalingo.writer import is_duckdb

from tests import fixtures

SOURCES = {s.id: s for s in load_registry()}


def loader(source_id):
    return LOADERS[source_id](SOURCES[source_id])


class LoaderTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name) / "raw"
        self.conn = sqlite3.connect(":memory:")
        apply_schema(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def load(self, source_id):
        item = loader(source_id)
        fixtures.install(self.raw, source_id, item.ref)
        return item.load(self.conn, self.raw)

    def rows(self, sql, *params):
        return self.conn.execute(sql, params).fetchall()

    def value(self, sql, *params):
        return self.conn.execute(sql, params).fetchone()[0]


class RegistryAndLoadersTest(unittest.TestCase):
    def test_every_loader_has_a_registry_entry_with_its_version(self):
        for source_id, cls in LOADERS.items():
            self.assertIn(source_id, SOURCES, f"{source_id} has a loader but no registry entry")
            self.assertIn(cls.ref, SOURCES[source_id].version, f"registry version of {source_id} should name {cls.ref}")


class ConcepticonTest(LoaderTestCase):
    def test_concept_sets_lists_and_relations(self):
        counts = self.load("concepticon")
        self.assertEqual(counts["concepts"], 5)  # 3 concept sets (placeholder 0 skipped) + 2 lists
        self.assertEqual(self.value("SELECT gloss FROM concepts WHERE concept_id = 'concepticon:1209'"), "EYE")
        self.assertEqual(self.value("SELECT kind FROM concepts WHERE concept_id = 'concepticon:list/Goddard-2011-63'"), "list")
        self.assertEqual(
            self.rows("SELECT from_id FROM relations WHERE relation_type = 'in_list' AND to_id = 'concepticon:list/Goddard-2011-63'"),
            [("concepticon:1409",)],
        )
        self.assertEqual(self.value("SELECT weight FROM relations WHERE relation_type = 'linked'"), 2.0)
        self.assertEqual(self.value("SELECT value_text FROM properties WHERE node_id = 'concepticon:list/Goddard-2011-63' AND property = 'tags'"), "primes; nsm")

    def test_reloading_replaces_rows(self):
        first = self.load("concepticon")
        second = loader("concepticon").load(self.conn, self.raw)
        self.assertEqual(first, second)
        self.assertEqual(self.value("SELECT COUNT(*) FROM sources"), 1)


class WoldTest(LoaderTestCase):
    def test_meanings_forms_scores_and_mappings(self):
        counts = self.load("wold")
        self.assertEqual(counts["forms"], 2)  # the empty form is skipped
        self.assertEqual(counts["mappings"], 2)
        self.assertAlmostEqual(self.value("SELECT value_num FROM properties WHERE node_id = 'wold:4-21' AND property = 'borrowed_score'"), 0.03)
        self.assertEqual(self.value("SELECT language FROM forms WHERE written_form = 'oog'"), "dutc1256")
        self.assertEqual(self.value("SELECT to_id FROM relations WHERE from_id = 'wold:form/13-4-21-1'"), "wold:4-21")
        self.assertEqual(self.value("SELECT to_id FROM mappings WHERE from_id = 'wold:4-21'"), "concepticon:1209")


class ClicsTest(LoaderTestCase):
    def test_colexifications_resolve_through_glosses(self):
        self.load("clics")
        self.assertEqual(self.rows("SELECT from_id, to_id, weight FROM relations"), [("clics:see", "clics:know", 12.0)])
        self.assertEqual(self.value("SELECT to_id FROM mappings WHERE from_id = 'clics:eye'"), "concepticon:1209")


class DatSemShiftTest(LoaderTestCase):
    def test_directed_shifts(self):
        self.load("datsemshift")
        self.assertEqual(self.rows("SELECT from_id, to_id, relation_type, weight FROM relations"), [("datsemshift:see", "datsemshift:know", "shift_polysemy", 2.0)])
        self.assertEqual(self.value("SELECT COUNT(*) FROM properties WHERE property = 'domain'"), 1)  # "N/a" dropped


class OewnTest(LoaderTestCase):
    def test_entries_synsets_and_relations(self):
        counts = self.load("oewn")
        self.assertEqual(counts["forms"], 3)
        self.assertEqual(counts["concepts"], 3)
        self.assertEqual(self.value("SELECT gloss FROM concepts WHERE concept_id = 'oewn:oewn-05317205-n'"), "eye")
        self.assertEqual(
            self.value("SELECT to_id FROM relations WHERE relation_type = 'derivation'"), "oewn:entry/oewn-sight-n"
        )
        self.assertEqual(self.value("SELECT to_id FROM relations WHERE relation_type = 'hypernym'"), "oewn:oewn-05316100-n")
        self.assertEqual(self.value("SELECT COUNT(*) FROM properties WHERE property = 'ili'"), 2)  # "in" (new) dropped


try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None


@unittest.skipUnless(duckdb, "DuckDB not installed")
class DuckDBMatchesSQLiteTest(LoaderTestCase):
    """The DuckDB bulk-insert path must produce the same rows as the SQLite path."""

    def test_same_counts_on_both_engines(self):
        duck = duckdb.connect(":memory:")
        apply_schema(duck)
        self.assertTrue(is_duckdb(duck), "DuckDB connections must take the bulk-insert path")
        self.assertFalse(is_duckdb(self.conn))
        try:
            for source_id in sorted(LOADERS):
                item = loader(source_id)
                fixtures.install(self.raw, source_id, item.ref)
                self.assertEqual(item.load(duck, self.raw), item.load(self.conn, self.raw), source_id)
            # loading twice must also work on DuckDB (delete, then insert the same keys)
            item = loader("concepticon")
            self.assertEqual(item.load(duck, self.raw), item.load(self.conn, self.raw))
        finally:
            duck.close()


class GlottologTest(LoaderTestCase):
    def test_languages_get_family_names(self):
        counts = self.load("glottolog")
        self.assertEqual(counts["languages"], 3)
        self.assertEqual(
            self.rows("SELECT name, iso639_3, family_name, macroarea FROM languages WHERE glottocode = 'dutc1256'"),
            [("Dutch", "nld", "Indo-European", "Eurasia")],
        )
        self.assertEqual(self.value("SELECT parent_language FROM languages WHERE glottocode = 'zeeu1238'"), "dutc1256")


class RawIntegrityTest(LoaderTestCase):
    def test_load_refuses_changed_raw_files(self):
        item = loader("datsemshift")
        folder = fixtures.install(self.raw, "datsemshift", item.ref)
        with open(folder / "parameters.csv", "a", encoding="utf-8") as handle:
            handle.write("tampered,row\n")
        with self.assertRaises(RuntimeError):
            item.load(self.conn, self.raw)


class CldfReaderTest(unittest.TestCase):
    def test_separators_components_and_zipped_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.concepticon(Path(tmp))
            data = Dataset(Path(tmp) / "Wordlist-metadata.json")
            lists = {row["ID"]: row for row in data.table("ContributionTable")}
            self.assertEqual(lists["Goddard-2011-63"]["Tags"], ["primes", "nsm"])
            self.assertEqual(lists["Ogden-1930-200"]["Tags"], [])
            self.assertTrue(data.has_table("concepts.csv"))
        with tempfile.TemporaryDirectory() as tmp:
            fixtures.clics(Path(tmp))
            data = Dataset(Path(tmp) / "StructureDataset-metadata.json")
            self.assertEqual(len(list(data.table("colexifications.csv"))), 2)  # read from colexifications.csv.zip


class FetchTest(unittest.TestCase):
    """Fetch from a local folder laid out like raw.githubusercontent.com/<repo>/<ref>/<path>."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.remote = root / "remote"
        self.raw = root / "raw"
        self.saved = fetch.RAW_GITHUB
        fetch.RAW_GITHUB = self.remote.as_uri()

    def tearDown(self):
        fetch.RAW_GITHUB = self.saved
        self.tmp.cleanup()

    def test_fetch_cldf_with_zipped_table_and_manifest(self):
        item = loader("clics")
        fixtures.clics(self.remote / item.repo / item.ref / "cldf")
        folder = item.fetch(self.raw)
        self.assertTrue((folder / "concepts.csv.zip").exists())
        self.assertTrue((folder / MANIFEST).exists())
        info = json.loads((folder / "SOURCE.json").read_text(encoding="utf-8"))
        self.assertEqual(info["ref"], "v1.0")
        self.assertTrue(item.is_fetched(self.raw))

        conn = sqlite3.connect(":memory:")
        apply_schema(conn)
        self.assertEqual(item.load(conn, self.raw)["relations"], 1)
        conn.close()

    def test_missing_file_is_reported_as_missing(self):
        with self.assertRaises(Exception) as caught:
            fetch.download((self.remote / "nope.csv").as_uri(), self.raw / "nope.csv")
        self.assertTrue(fetch.is_missing(caught.exception))


if __name__ == "__main__":
    unittest.main()
