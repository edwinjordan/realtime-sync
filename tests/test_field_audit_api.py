import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

module_path = Path(__file__).resolve().parents[1] / "field_audit_api.py"
spec = importlib.util.spec_from_file_location("field_audit_api", module_path)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class SyncFieldAuditFromExcelTests(unittest.TestCase):
    def setUp(self):
        self.original_excel_config = api.EXCEL_CONFIG
        self.original_mysql_config = api.MYSQL_CONFIG
        self.original_table_config = api.TABLE_CONFIG
        self.original_unique_columns = api.UNIQUE_COLUMNS
        api.EXCEL_CONFIG = {"file_path": "field_audit.xlsx", "sheet_name": "Sheet1"}
        api.MYSQL_CONFIG = {"database": "test"}
        api.TABLE_CONFIG = {
            "name": "field_audit",
            "update_existing": True,
            "insert_exclude_columns": ["id", "created_at", "updated_at"],
        }
        api.UNIQUE_COLUMNS = ["field_number"]

    def tearDown(self):
        api.EXCEL_CONFIG = self.original_excel_config
        api.MYSQL_CONFIG = self.original_mysql_config
        api.TABLE_CONFIG = self.original_table_config
        api.UNIQUE_COLUMNS = self.original_unique_columns

    def test_post_sync_reads_excel_updates_existing_and_inserts_new_rows(self):
        excel_rows = [
            {
                "Field Number": "F-001",
                "Season": "2026",
                "Gen 5 Closed Out Date": 0.0,
            },
            {
                "Field Number": "F-002",
                "Season": "2026",
                "Gen 5 Closed Out Date": 0.0,
            },
            {"Field Number": None, "Season": "2026"},
        ]
        with (
            patch.object(api.sync_service, "read_excel_rows", return_value=excel_rows) as read_excel,
            patch.object(
                api.sync_service,
                "get_table_column_types",
                return_value={
                    "field_number": "varchar(100)",
                    "season": "varchar(50)",
                    "gen5_closed_out_date": "date",
                },
            ),
            patch.object(
                api.sync_service,
                "get_existing_keys",
                return_value={("F-001",)},
            ),
            patch.object(
                api.sync_service,
                "upsert_rows",
                return_value=(1, 1, 0),
            ) as upsert_rows,
        ):
            result = api.sync_field_audit_from_excel()

        read_excel.assert_called_once_with(api.EXCEL_CONFIG)
        prepared_rows = upsert_rows.call_args.args[2]
        self.assertEqual(len(prepared_rows), 3)
        self.assertEqual(upsert_rows.call_args.args[4], {("F-001",)})
        self.assertEqual(prepared_rows[1]["field_number"], "F-002")
        self.assertIsNone(prepared_rows[1]["gen5_closed_out_date"])
        self.assertEqual(
            result,
            {
                "status": "completed",
                "excel_rows": 3,
                "valid_key_rows": 2,
                "skipped_rows": 1,
                "new_rows": 1,
                "inserted_rows": 1,
                "updated_rows": 1,
                "failed_rows": 0,
            },
        )

    def test_sync_returns_zero_counts_when_excel_is_empty(self):
        with patch.object(api.sync_service, "read_excel_rows", return_value=[]):
            result = api.sync_excel_to_database()

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["inserted_rows"], 0)

    def test_sync_rejects_a_concurrent_request(self):
        api.SYNC_LOCK.acquire()
        try:
            with self.assertRaises(HTTPException) as raised:
                api.sync_field_audit_from_excel()
        finally:
            api.SYNC_LOCK.release()

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
