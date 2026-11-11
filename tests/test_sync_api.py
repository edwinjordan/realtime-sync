import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

module_path = Path(__file__).resolve().parents[1] / "sync_excel_to_mysql.py"
spec = importlib.util.spec_from_file_location("sync_excel_to_mysql", module_path)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class BuildPayloadTests(unittest.TestCase):
    def test_build_payload_uses_mapping_and_defaults(self):
        row = {
            "bulan": "Januari",
            "chemical_code": "CHEM-001",
            "qty": 100.5,
            "chemical_name": "Pestisida A",
            "region": "1",
            "tahun": 2026,
        }
        api_cfg = {
            "field_map": {
                "chemical_trans_bulan": "bulan",
                "chemical_trans_detail_chemical": "chemical_code",
                "chemical_trans_detail_jumlah": "qty",
                "chemical_trans_detail_chemical_nama": "chemical_name",
                "chemical_trans_region": "region",
                "chemical_trans_tahun": "tahun",
            },
            "defaults": {
                "chemical_trans_region": "1",
            },
        }

        payload = sync.build_chemical_transaction_payload(row, api_cfg)

        self.assertEqual(payload["chemical_trans_bulan"], "Januari")
        self.assertEqual(payload["chemical_trans_detail_chemical"], "CHEM-001")
        self.assertEqual(payload["chemical_trans_detail_jumlah"], 100.5)
        self.assertEqual(payload["chemical_trans_detail_chemical_nama"], "Pestisida A")
        self.assertEqual(payload["chemical_trans_region"], "1")
        self.assertEqual(payload["chemical_trans_tahun"], 2026)


class FieldAuditMappingTests(unittest.TestCase):
    def test_map_row_to_table_uses_schema_columns_and_excludes_generated_fields(self):
        row = {
            "Season": "2026",
            "Field Number": "F-001",
            "Farmer Name": "Budi",
            "Gen 1 Audit Date": "2026-01-15",
            "Planting \n Ratio": "4:2",
        }
        table_cfg = {"insert_exclude_columns": ["id", "created_at", "updated_at"]}

        mapped = sync.map_row_to_table(
            row,
            table_cfg,
            {
                "season",
                "field_number",
                "farmer_name",
                "gen1_audit_date",
                "planting_ratio",
                "id",
                "created_at",
                "updated_at",
            },
        )

        self.assertEqual(
            mapped,
            {
                "season": "2026",
                "field_number": "F-001",
                "farmer_name": "Budi",
                "gen1_audit_date": "2026-01-15",
                "planting_ratio": "4:2",
            },
        )

    def test_select_new_rows_deduplicates_by_composite_key(self):
        rows = [
            {"season": "2026", "field_number": "F-001", "farmer_name": "Updated name"},
            {"season": "2026", "field_number": "F-002", "farmer_name": "Siti"},
            {"season": "2026", "field_number": "F-002", "farmer_name": "Duplicate row"},
            {"season": "2026", "field_number": None, "farmer_name": "Missing key"},
        ]
        existing_keys = {("2026", "F-001")}

        new_rows = sync.select_new_rows(rows, existing_keys, ["season", "field_number"])

        self.assertEqual(len(new_rows), 1)
        self.assertEqual(new_rows[0]["field_number"], "F-002")

    def test_map_row_converts_zero_date_to_null_and_excel_serial_to_date(self):
        row = {
            "Gen 5 Closed Out Date": 0.0,
            "Gen 4 Audit Date": 2.0,
        }

        mapped = sync.map_row_to_table(
            row,
            {},
            {"gen5_closed_out_date", "gen4_audit_date"},
            {"gen5_closed_out_date": "date", "gen4_audit_date": "date"},
        )

        self.assertIsNone(mapped["gen5_closed_out_date"])
        self.assertEqual(mapped["gen4_audit_date"].isoformat(), "1900-01-02")


class UpsertRowsTests(unittest.TestCase):
    def test_upsert_updates_existing_key_and_inserts_new_key(self):
        class Cursor:
            def __init__(self):
                self.statements = []

            def execute(self, sql, values):
                self.statements.append((sql, values))

            def close(self):
                pass

        class Connection:
            def __init__(self):
                self.cursor_instance = Cursor()
                self.committed = False

            def cursor(self):
                return self.cursor_instance

            def commit(self):
                self.committed = True

            def close(self):
                pass

        connection = Connection()
        rows = [
            {"field_number": "F-1", "farmer_name": "Updated", "id": 80},
            {"field_number": "F-2", "farmer_name": "New", "created_at": None},
        ]

        with patch.object(sync.mysql.connector, "connect", return_value=connection):
            result = sync.upsert_rows(
                {"database": "test"},
                {"name": "field_audits"},
                rows,
                ["field_number"],
                {("F-1",)},
            )

        self.assertEqual(result, (1, 1, 0))
        self.assertTrue(connection.committed)
        update_sql, update_values = connection.cursor_instance.statements[0]
        insert_sql, insert_values = connection.cursor_instance.statements[1]
        self.assertTrue(update_sql.startswith("UPDATE `field_audits`"))
        self.assertNotIn("`id` =", update_sql)
        self.assertEqual(update_values, ["Updated", "F-1"])
        self.assertTrue(insert_sql.startswith("INSERT INTO `field_audits`"))
        self.assertEqual(insert_values, ["F-2", "New", None])


if __name__ == "__main__":
    unittest.main()
