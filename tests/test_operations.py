"""The operations library on the fixture sources (step 6)."""

from semalingo.linking import link
from semalingo.ops import Graph

from tests.test_loaders import LoaderTestCase

EYE, SEE, KNOW = "concepticon:1209", "concepticon:1409", "concepticon:1410"


class OperationsTest(LoaderTestCase):
    def setUp(self):
        super().setUp()
        for source in ("glottolog", "concepticon", "oewn", "sumo", "cili", "clics", "norare", "lexibank", "subtlex-nl"):
            self.load(source)
        link(self.conn)
        self.graph = Graph(self.conn)

    def test_languages_by_code_or_name(self):
        self.assertEqual(self.graph.language("nl"), "dutc1256")
        self.assertEqual(self.graph.language("Dutch"), "dutc1256")
        self.assertEqual(self.graph.language("nld"), "dutc1256")
        self.assertEqual(self.graph.language("stan1293"), "stan1293")

    def test_lookup_finds_concepts_and_what_words_mean(self):
        result = self.graph.lookup("eye")
        self.assertIn(EYE, [c["id"] for c in result["concepts"]])
        concepticon_words = [w for w in result["words"] if w["source"] == "concepticon"][0]
        self.assertEqual([m["id"] for m in concepticon_words["means"]], [EYE])
        self.assertIn("concepticon", [s["id"] for s in result["provenance"]["sources"]])
        dutch = self.graph.lookup("oog", language="nl")
        self.assertEqual({w["language"] for w in dutch["words"]}, {"dutc1256"})

    def test_lookup_of_a_node_id_describes_it(self):
        result = self.graph.lookup(EYE)
        self.assertEqual(result["node"]["label"], "EYE")
        self.assertIn({"property": "definition", "value": "The organ of sight.", "source": "concepticon"}, result["properties"])
        self.assertTrue(any(c["type"] == "expresses" and c["direction"] == "in" for c in result["edge_counts"]))

    def test_neighbours_walk_the_sumo_hierarchy(self):
        result = self.graph.neighbours("sumo:Eye", hops=3, edge_types=["subclass_of"], direction="out")
        hops = {n["id"]: n["hop"] for n in result["nodes"]}
        self.assertEqual(hops, {"sumo:Organ": 1, "sumo:AnimalAnatomicalStructure": 2})

    def test_norms_reach_the_words_of_a_concept(self):
        result = self.graph.norms(EYE, constructs=["aoa"])
        values = {(r["source"], r["property"]): r for r in result["values"]}
        aoa = values[("norare", "Kuperman-2012-AoA-ENGLISH_AOA_MEAN")]
        self.assertEqual((aoa["value"], aoa["on"]), (3.6, "eye (stan1293)"))
        self.assertTrue(aoa["via"].startswith("expresses norare:concept/1209"))
        self.assertEqual(set(result["constructs"]), {"aoa"})

    def test_colexifications(self):
        result = self.graph.colexifications(SEE)
        self.assertEqual(result["clics"], [{"concept": KNOW, "label": KNOW, "families": 12}])

    def test_path_through_wordnet(self):
        result = self.graph.path(EYE, "cili:i68829")
        steps = [(e["from"], e["to"], e["type"]) for e in result["paths"][0]["edges"]]
        self.assertEqual(steps, [(EYE, "oewn:oewn-05317205-n", "mapping:close"), ("oewn:oewn-05317205-n", "cili:i68829", "mapping:exact")])
        self.assertEqual(result["paths"][0]["edges"][0]["method"], "gloss")  # the WordNet link is a proposal
        self.assertEqual(result["provenance"]["mapping_methods"], {"gloss": 1, "imported": 1})
        # Concepticon's "linked" edges are left out unless asked for
        self.assertEqual(self.graph.path(EYE, SEE, max_hops=1)["paths"], [])
        self.assertEqual(len(self.graph.path(EYE, SEE, max_hops=1, edge_types=["linked"])["paths"]), 1)

    def test_words_of_a_concept_in_a_language(self):
        result = self.graph.words(EYE, language="nl")
        words = {w["word"]: w for w in result["languages"][0]["words"]}
        self.assertEqual(result["languages"][0]["name"], "Dutch")
        self.assertIn("oog", words)
        self.assertTrue(words["oːx"]["phonetic"])  # Lexibank's form, through its EYE concept

    def test_compare(self):
        result = self.graph.compare(EYE, SEE)
        self.assertEqual((result["a"]["node"]["label"], result["b"]["node"]["label"]), ("EYE", "SEE"))
        self.assertIn("aoa", result["a"]["norms"])

    def test_sql_is_read_only(self):
        result = self.graph.sql("SELECT gloss FROM concepts WHERE concept_id = 'concepticon:1209'")
        self.assertEqual(result["rows"], [["EYE"]])
        for query in ("DROP TABLE forms", "SELECT 1; DELETE FROM forms", "SELECT * FROM read_csv('/etc/passwd')",
                      "WITH x AS (SELECT 1) INSERT INTO forms SELECT * FROM x"):
            self.assertIn("error", self.graph.sql(query), query)
        self.assertEqual(self.graph.sql("SELECT 'drop table' AS t")["rows"], [["drop table"]])  # words inside strings are fine


class GoldenTest(OperationsTest):
    def test_paths_and_checks(self):
        from semalingo.golden import check, run, values_at

        data = {"a": [{"b": 1}, {"b": 2}], "c": {"d": [5]}}
        self.assertEqual(values_at(data, "a[*].b"), [1, 2])
        self.assertEqual(values_at(data, "a[1].b"), [2])
        self.assertEqual(values_at(data, "c.d[0]"), [5])
        self.assertIsNone(check(data, {"at": "a[*].b", "contains": 2}))
        self.assertIn("does not contain", check(data, {"at": "a[*].b", "contains": 3}))
        self.assertIn("below", check(data, {"at": "a[*].b", "min": 2}))
        results = run(self.graph, [
            {"question": "EYE by name", "operation": "lookup", "args": ["eye"],
             "expect": [{"at": "concepts[*].id", "contains": EYE}]},
            {"question": "no such operation", "operation": "nothing", "args": []},
        ])
        self.assertEqual([bool(p) for _, p in results], [False, True])
