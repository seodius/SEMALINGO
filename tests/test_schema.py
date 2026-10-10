"""The core schema runs on SQLite (always) and DuckDB (when installed, as in CI)."""

import sqlite3
import unittest

from semalingo.db import CORE_TABLES, apply_schema, schema_sql, statements

try:
    import duckdb
except ImportError:  # pragma: no cover
    duckdb = None


class SchemaChecks:
    """Shared checks; subclasses provide connect() and the engine's integrity error."""

    def setUp(self):
        self.conn = self.connect()
        apply_schema(self.conn)

    def tearDown(self):
        self.conn.close()

    def insert_mapping(self, mapping_type="exact", confidence=0.9, method="gloss", reviewer=None):
        self.conn.execute(
            "INSERT INTO mappings (from_id, to_id, mapping_type, confidence, method, reviewer) VALUES (?, ?, ?, ?, ?, ?)",
            ["concepticon:1209", "oewn:eye-n-01", mapping_type, confidence, method, reviewer],
        )

    def test_all_core_tables_exist(self):
        for table in CORE_TABLES:
            self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchall()

    def test_schema_can_be_applied_twice(self):
        apply_schema(self.conn)

    def test_valid_mapping_is_accepted(self):
        self.insert_mapping()

    def test_same_as_is_not_a_mapping_type(self):
        with self.assertRaises(self.integrity_error):
            self.insert_mapping(mapping_type="sameAs")

    def test_confidence_must_be_between_0_and_1(self):
        with self.assertRaises(self.integrity_error):
            self.insert_mapping(confidence=1.5)

    def test_manual_mapping_needs_a_reviewer(self):
        with self.assertRaises(self.integrity_error):
            self.insert_mapping(method="manual")
        self.insert_mapping(method="manual", reviewer="seodius")

    def test_property_needs_a_value(self):
        with self.assertRaises(self.integrity_error):
            self.conn.execute(
                "INSERT INTO properties (node_id, source_id, property) VALUES (?, ?, ?)",
                ["kuperman-aoa:eye", "kuperman-aoa", "aoa_rated"],
            )

    def test_unknown_concept_kind_is_rejected(self):
        with self.assertRaises(self.integrity_error):
            self.conn.execute(
                "INSERT INTO concepts (concept_id, source_id, kind) VALUES (?, ?, ?)",
                ["concepticon:1209", "concepticon", "bubble"],
            )


class SQLiteSchemaTest(SchemaChecks, unittest.TestCase):
    integrity_error = sqlite3.IntegrityError

    def connect(self):
        return sqlite3.connect(":memory:")


@unittest.skipUnless(duckdb, "DuckDB not installed")
class DuckDBSchemaTest(SchemaChecks, unittest.TestCase):
    integrity_error = duckdb.Error if duckdb else Exception

    def connect(self):
        return duckdb.connect(":memory:")


class StatementSplitTest(unittest.TestCase):
    def test_one_statement_per_table(self):
        creates = [s for s in statements(schema_sql()) if s.upper().startswith("CREATE TABLE")]
        self.assertEqual(len(creates), len(CORE_TABLES))


if __name__ == "__main__":
    unittest.main()
