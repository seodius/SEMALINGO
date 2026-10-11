import tempfile
import unittest
from pathlib import Path

from semalingo import ops
from semalingo.ids import make_node_id, split_node_id
from semalingo.raw import verify_checksums, write_checksums


class NodeIdTest(unittest.TestCase):
    def test_round_trip(self):
        node = make_node_id("concepticon", 1209)
        self.assertEqual(node, "concepticon:1209")
        self.assertEqual(split_node_id(node), ("concepticon", "1209"))

    def test_local_id_may_contain_colons(self):
        self.assertEqual(split_node_id("oewn:oewn-eye-n:01"), ("oewn", "oewn-eye-n:01"))

    def test_bad_ids_are_rejected(self):
        for bad in ("eye", ":1209", "Concepticon:1209", "concepticon:"):
            with self.assertRaises(ValueError):
                split_node_id(bad)
        with self.assertRaises(ValueError):
            make_node_id("concepticon", "two words")


class ChecksumTest(unittest.TestCase):
    def test_manifest_detects_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "words.tsv").write_text("eye\t1\n", encoding="utf-8")
            (folder / "sub").mkdir()
            (folder / "sub" / "more.tsv").write_text("see\t2\n", encoding="utf-8")
            write_checksums(folder)
            self.assertEqual(verify_checksums(folder), [])

            (folder / "words.tsv").write_text("eye\t9\n", encoding="utf-8")
            (folder / "extra.tsv").write_text("watch\n", encoding="utf-8")
            (folder / "sub" / "more.tsv").unlink()
            problems = verify_checksums(folder)
            self.assertIn("changed: words.tsv", problems)
            self.assertIn("missing: sub/more.tsv", problems)
            self.assertIn("not in manifest: extra.tsv", problems)

    def test_missing_manifest_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(verify_checksums(Path(tmp)))


class OperationsContractTest(unittest.TestCase):
    def test_the_six_operations_exist(self):
        for name in ("lookup", "neighbours", "norms", "colexifications", "path", "compare"):
            self.assertTrue(callable(getattr(ops, name)))



if __name__ == "__main__":
    unittest.main()
