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

    def test_glosses_in_several_languages(self):
        counts = self.load("concepticon")
        self.assertEqual(counts["forms"], 3)
        self.assertEqual(self.value("SELECT written_form FROM forms WHERE language = 'dutc1256'"), "oog")
        self.assertEqual(
            self.rows("SELECT to_id, relation_type FROM relations WHERE from_id = 'concepticon:gloss/Ogden-1930-200-1-2' ORDER BY relation_type"),
            [("concepticon:1209", "expresses"), ("concepticon:list/Ogden-1930-200", "in_list")],
        )
        # an unmapped gloss is kept, without an "expresses" edge
        self.assertEqual(self.value("SELECT COUNT(*) FROM relations WHERE from_id = 'concepticon:gloss/Ogden-1930-200-2-1'"), 1)

    def test_fetch_again_when_a_needed_table_is_missing(self):
        item = loader("concepticon")
        folder = fixtures.install(self.raw, "concepticon", item.ref)
        self.assertTrue(item.is_fetched(self.raw))
        (folder / "glosses.csv").unlink()
        from semalingo.raw import write_checksums
        write_checksums(folder)
        self.assertFalse(item.is_fetched(self.raw))

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


class FrequencyLoadersTest(LoaderTestCase):
    def test_subtlex_nl_skips_punctuation_and_numbers(self):
        counts = self.load("subtlex-nl")
        self.assertEqual(counts["forms"], 2)
        self.assertEqual(self.value("SELECT language FROM forms WHERE form_id = 'subtlex-nl:oog'"), "dutc1256")
        self.assertEqual(self.value("SELECT value_text FROM properties WHERE node_id = 'subtlex-nl:oog' AND property = 'dominant_pos'"), "N")
        zipf = dict(self.rows("SELECT node_id, value_num FROM properties WHERE property = 'zipf'"))
        self.assertGreater(zipf["subtlex-nl:ik"], zipf["subtlex-nl:oog"])

    def test_subtlex_uk_and_us(self):
        self.assertEqual(self.load("subtlex-uk")["forms"], 2)
        self.assertEqual(self.load("subtlex-us")["forms"], 2)
        self.assertEqual(self.value("SELECT value_num FROM properties WHERE node_id = 'subtlex-us:eye' AND property = 'cd_count'"), 3000.0)

    def test_childlex_words_lemmas_and_links(self):
        counts = self.load("childlex")
        self.assertEqual(counts["forms"], 3)  # Auge, Augen, lemma/Auge
        self.assertEqual(
            self.rows("SELECT from_id, weight FROM relations WHERE to_id = 'childlex:lemma/Auge' ORDER BY from_id"),
            [("childlex:Auge", 900.0), ("childlex:Augen", 700.0)],
        )


class NorareTest(LoaderTestCase):
    def test_norms_on_words_with_property_types(self):
        counts = self.load("norare")
        self.assertEqual(counts["forms"], 3)
        self.assertEqual(counts["concepts"], 4)  # two concept sets, two studies
        self.assertEqual(counts["property_types"], 3)
        self.assertEqual(counts["mappings"], 2)
        eye = "norare:form/Kuperman-2012-AoA-stan1293-1"
        self.assertEqual(self.value("SELECT language FROM forms WHERE form_id = ?", eye), "stan1293")
        self.assertEqual(self.value("SELECT value_num FROM properties WHERE node_id = ? AND property = 'Kuperman-2012-AoA-ENGLISH_AOA_MEAN'", eye), 3.6)
        self.assertEqual(self.value("SELECT value_text FROM properties WHERE node_id = ? AND property LIKE '%PERCEPTUAL_DOMINANT'", eye), "Visual")
        # a zero is a value, not a missing value
        self.assertEqual(self.value("SELECT value_num FROM properties WHERE property = 'Speed-2021-Sensorimotor-DUTCH_VISUAL_MEAN'"), 0.0)
        self.assertEqual(
            self.rows("SELECT construct, statistic, language FROM property_types WHERE property = 'Kuperman-2012-AoA-ENGLISH_AOA_MEAN'"),
            [("aoa", "mean", "stan1293")],
        )
        self.assertEqual(
            sorted(self.rows("SELECT to_id, relation_type FROM relations WHERE from_id = ?", eye)),
            [("norare:concept/1209", "expresses"), ("norare:dataset/Kuperman-2012-AoA", "in_list")],
        )
        self.assertEqual(self.value("SELECT to_id FROM mappings WHERE from_id = 'norare:concept/1209'"), "concepticon:1209")

    def test_frequency_sources_describe_their_properties(self):
        self.load("subtlex-nl")
        self.assertEqual(
            self.rows("SELECT property, construct FROM property_types WHERE source_id = 'subtlex-nl' AND property IN ('zipf', 'cd_count') ORDER BY property"),
            [("cd_count", "contextual diversity"), ("zipf", "frequency")],
        )


class GlossMatchingTest(LoaderTestCase):
    def test_lookup_tables_give_shares_per_gloss(self):
        counts = self.load("concepticon-maps")
        self.assertEqual(counts["forms"], 7)  # en: eye, eyes, see, watch; nl: oog, zien, kijken
        shares = dict(self.rows("SELECT to_id, confidence FROM mappings WHERE from_id = 'concepticon-maps:en/watch'"))
        self.assertEqual(shares, {"concepticon:1650": 0.7, "concepticon:3349": 0.3})
        self.assertEqual(self.value("SELECT language FROM forms WHERE form_id = 'concepticon-maps:nl/kijken'"), "dutc1256")

    def test_gloss_keys(self):
        from semalingo.matching import gloss_keys
        self.assertEqual(gloss_keys("the Eyes", "stan1293"), ["eyes"])
        self.assertEqual(gloss_keys("to see (perceive)", "stan1293"), ["see"])
        self.assertEqual(gloss_keys("zien, kijken", "dutc1256"), ["zien", "kijken"])
        self.assertEqual(gloss_keys("de ogen", "dutc1256"), ["de ogen"])  # leading words are only stripped for English
        self.assertEqual(gloss_keys("anxiety, worry", "stan1293", split=False), ["anxiety, worry"])

    def test_words_of_other_sources_get_gloss_mappings(self):
        from semalingo.matching import build_index, match_source
        self.load("concepticon-maps")
        self.load("subtlex-nl")
        self.load("oewn")
        index = build_index(self.conn)
        self.assertEqual(match_source(self.conn, "subtlex-nl", index), {"forms": 2, "matched": 1, "mappings": 1})
        self.assertEqual(
            self.rows("SELECT to_id, mapping_type, confidence, method FROM mappings WHERE from_id = 'subtlex-nl:oog'"),
            [("concepticon:1209", "close", 1.0, "gloss")],
        )
        result = match_source(self.conn, "oewn", index, min_share=0.5)
        self.assertEqual(result["matched"], 2)  # eye, see; not sight
        # matching again replaces the earlier gloss mappings
        self.assertEqual(match_source(self.conn, "oewn", index, min_share=0.5), result)
        self.assertEqual(self.value("SELECT COUNT(*) FROM mappings WHERE method = 'gloss' AND from_id LIKE 'oewn:%'"), 2)


class WordListsTest(LoaderTestCase):
    def categories(self, source_id):
        return dict(self.rows(
            "SELECT f.written_form, p.value_text FROM forms f JOIN properties p ON p.node_id = f.form_id "
            "AND p.property = 'category' WHERE f.source_id = ?", source_id))

    def props(self, node):
        return dict(self.rows("SELECT property, COALESCE(value_text, value_num) FROM properties WHERE node_id = ?", node))

    def test_basic_english_categories(self):
        self.assertEqual(self.load("basic-english")["forms"], 14)  # 15 links, watch twice
        categories = self.categories("basic-english")
        self.assertEqual(categories["watch"], "operations; things (picturable)")
        self.assertEqual(categories["look"], "things (general)")
        self.assertEqual(categories["bad"], "qualities (opposites)")
        self.assertNotIn("Pictures of these 200 words", categories)
        self.assertEqual(self.value("SELECT language FROM forms WHERE form_id = 'basic-english:eye'"), "stan1293")

    def test_1000_basic_words(self):
        self.assertEqual(self.load("wiktionary-1000-basic")["forms"], 5)

    def test_combined_list(self):
        self.assertEqual(self.load("basic-english-combined")["forms"], 9)  # working twice
        categories = self.categories("basic-english-combined")
        self.assertEqual(categories["working"], "endings; compound")
        self.assertEqual(categories["meter"], "addendum")
        self.assertIn("micro-", categories)

    def test_voa_definitions_and_parts_of_speech(self):
        self.load("voa-special-english")
        self.assertEqual(self.props("voa-special-english:a"), {"category": "core", "pos": "ad", "definition": "one; any; each", "variant": "an"})
        love = self.props("voa-special-english:love")
        self.assertEqual(love["pos"], "v, n")
        self.assertEqual(love["definition"], "to like very much; a strong, kind emotion for someone or something; opposite hate")
        self.assertEqual(self.props("voa-special-english:un-")["category"], "common prefixes")
        self.assertEqual(self.props("voa-special-english:carry_out")["definition"], 'to do; to put into effect ("Please carry out the plan.")')
        self.assertEqual(self.categories("voa-special-english")["adverb"], "parts of speech")

    def test_misspellings(self):
        self.assertEqual(self.load("simple-misspellings")["forms"], 4)
        self.assertEqual(self.props("simple-misspellings:comfortable")["misspellings"], "confortable")
        self.assertEqual(self.props("simple-misspellings:accidently")["misspellings"], "accidentaly")

    def test_nsm_primes_and_exponents(self):
        counts = self.load("nsm-primes")
        self.assertEqual(counts["concepts"], 20)
        glosses = dict(self.rows("SELECT concept_id, gloss FROM concepts"))
        self.assertEqual(glosses["nsm-primes:something-thing"], "SOMETHING~THING")
        self.assertEqual(glosses["nsm-primes:other-else-another"], "OTHER~ELSE~ANOTHER")
        self.assertEqual(glosses["nsm-primes:be-someone-something"], "BE (SOMEONE/SOMETHING)")
        self.assertEqual(
            sorted(r[0] for r in self.rows("SELECT to_id FROM relations WHERE from_id = 'nsm-primes:form/be'")),
            ["nsm-primes:be-someone-something", "nsm-primes:be-somewhere"],
        )
        self.assertEqual(self.value("SELECT to_id FROM relations WHERE from_id = 'nsm-primes:form/mine'"), "nsm-primes:is-mine")
        self.assertEqual(self.props("nsm-primes:i")["category"], "Substantives")


class ManualSourceTest(LoaderTestCase):
    def test_missing_manual_file_explains_add_file(self):
        from semalingo.loaders import ManualSourceMissing

        with self.assertRaises(ManualSourceMissing) as caught:
            loader("subtlex-uk").fetch(self.raw)
        self.assertIn("semalingo add-file subtlex-uk", str(caught.exception))

    def test_add_file_copies_checksums_and_loads(self):
        download = Path(self.tmp.name) / "my downloads"
        fixtures.subtlex_uk(download)
        item = loader("subtlex-uk")
        item.add_file(self.raw, download / "SUBTLEX-UK_all.xlsx")
        self.assertTrue(item.is_fetched(self.raw))
        self.assertEqual(item.load(self.conn, self.raw)["forms"], 2)


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
