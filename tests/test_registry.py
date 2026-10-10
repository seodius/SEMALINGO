import unittest
from pathlib import Path

from semalingo.cli import licences_path
from semalingo.registry import default_registry_path, licence_table, load_registry, read_raw, validate

REGISTRY = default_registry_path()


def entry(**overrides):
    base = {
        "id": "example",
        "name": "Example",
        "wave": "first",
        "unit": "forms",
        "homepage": "https://example.org",
        "download": "https://example.org/data",
        "format": "TSV",
        "version": "1.0",
        "licence": "CC BY 4.0",
        "redistributable": "yes",
        "used_by": ["Q1"],
        "checked": False,
        "notes": "",
    }
    base.update(overrides)
    return base


class RegistryFileTest(unittest.TestCase):
    def test_registry_is_valid(self):
        self.assertEqual(validate(read_raw(REGISTRY)), [])

    def test_every_first_wave_source_serves_a_question(self):
        for source in load_registry(REGISTRY):
            if source.wave == "first":
                self.assertTrue(source.used_by, f"{source.id} serves no exit question")

    def test_data_licences_file_is_up_to_date(self):
        generated = licence_table(load_registry(REGISTRY)) + "\n"
        committed = licences_path(REGISTRY).read_text(encoding="utf-8")
        self.assertEqual(committed, generated, "run `semalingo licences --write`")


class ValidationRulesTest(unittest.TestCase):
    def test_valid_entry_passes(self):
        self.assertEqual(validate([entry()]), [])

    def test_duplicate_ids_are_rejected(self):
        problems = validate([entry(), entry()])
        self.assertTrue(any("duplicate id" in p for p in problems))

    def test_bad_id_is_rejected(self):
        self.assertTrue(validate([entry(id="Not A Slug")]))

    def test_unknown_wave_is_rejected(self):
        self.assertTrue(validate([entry(wave="third")]))

    def test_unquoted_yaml_no_is_caught(self):
        # YAML reads a bare `no` as False; the registry must quote it.
        self.assertTrue(validate([entry(redistributable=False)]))

    def test_checked_entry_may_not_keep_todo(self):
        problems = validate([entry(checked=True, licence="TODO")])
        self.assertTrue(any("still TODO" in p for p in problems))

    def test_unknown_question_is_rejected(self):
        self.assertTrue(validate([entry(used_by=["Q9"])]))

    def test_missing_and_unknown_fields_are_reported(self):
        broken = entry(colour="blue")
        del broken["licence"]
        problems = validate([broken])
        self.assertTrue(any("missing fields licence" in p for p in problems))
        self.assertTrue(any("unknown fields colour" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
