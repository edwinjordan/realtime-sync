import datetime
import decimal
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


class VegetativePhaseApiTests(unittest.TestCase):
    def setUp(self):
        self.original_mysql_config = api.MYSQL_CONFIG
        self.original_table_name = api.TABLE_NAME
        api.MYSQL_CONFIG = {"database": "test"}
        api.TABLE_NAME = "field_audit"

    def tearDown(self):
        api.MYSQL_CONFIG = self.original_mysql_config
        api.TABLE_NAME = self.original_table_name

    def test_format_vegetative_row_contains_all_50_keys_in_order(self):
        sample_db_row = {
            "season": "DS26",
            "type_corn": "Field Corn",
            "field_number": "DC6715080",
            "farmer_name": "pak mashud tebu",
            "grower": "Fitrianingsasi",
            "hybrid": "AX09",
            "actual_area_planted": decimal.Decimal("0.16"),
            "discard_area_ha": decimal.Decimal("0.00"),
            "effective_area_ha": decimal.Decimal("0.16"),
            "previous_crop_corn": "Not Corn",
            "planting_ratio": "04:02:00",
            "planting_space": "60x18",
            "split_planting": "-3,0,0",
            "female_planting_date_actual": datetime.date(2026, 4, 24),
            "hamlet": None,
            "village": None,
            "sub_district": None,
            "district": None,
            "province": None,
            "flagging_final": "GF",
            "field_assistant": "Chairunnisa Faza Nabillah",
            "supervisor": "Alfian Dwi Purnomo",
            "manager": "Anggi Yanuar Yanto",
            "region": "Region 3",
            "corr_tagging": "-7.992958,112.747986",
            "qa_spv": "Tonny Andhi Jaya",
            "qa_fi": "David Billy Jepryanto",
            "co_detasseling": "Nisa jep",
            "audit_date": datetime.date(2026, 5, 18),
            "audit_week": "21.0",
            "field_size_ha": decimal.Decimal("0.16"),
            "male_split": "Yes",
            "sowing_ratio": "05:02:00",
            "split_field": "No",
            "previous_crop": "Not Corn",
            "one_seed_hole": "Yes",
            "isolation_problem": "No",
            "crop_uniformity": "Fair",
            "crop_health": "Poor",
            "roguing_status": "On Going",
            "lsv_status": "Moderate",
            "offtype_m": "0.0",
            "offtype_f": ">0",
            "poi_accuracy": "Not Valid",
            "rev_planting_date": datetime.date(2026, 4, 24),
            "decision": "Pass with Note",
            "action_needed": "Roguing",
            "pld_reason": None,
            "flagging": "GF",
            "remarks": "-",
            # extra non-vegetative columns in table:
            "gen1_audit_date": datetime.date(2026, 6, 24),
            "harvested_area_ha": decimal.Decimal("0.16"),
        }

        formatted = api.format_vegetative_row(sample_db_row)
        self.assertEqual(len(formatted), 50)
        self.assertEqual(list(formatted.keys()), api.VEGETATIVE_COLUMNS)
        self.assertEqual(formatted["actual_area_planted"], 0.16)
        self.assertEqual(formatted["discard_area_ha"], 0)
        self.assertEqual(formatted["female_planting_date_actual"], "2026-04-24")
        self.assertEqual(formatted["remarks"], "-")
        self.assertNotIn("gen1_audit_date", formatted)
        self.assertNotIn("harvested_area_ha", formatted)

    def test_list_vegetative_queries_and_formats(self):
        mock_raw = [{
            "season": "DS26",
            "type_corn": "Field Corn",
            "field_number": "DC6715080",
            "farmer_name": "pak mashud tebu",
            "grower": "Fitrianingsasi",
            "hybrid": "AX09",
            "actual_area_planted": decimal.Decimal("0.16"),
            "discard_area_ha": decimal.Decimal("0.00"),
            "effective_area_ha": decimal.Decimal("0.16"),
            "previous_crop_corn": "Not Corn",
            "planting_ratio": "04:02:00",
            "planting_space": "60x18",
            "split_planting": "-3,0,0",
            "female_planting_date_actual": datetime.date(2026, 4, 24),
            "hamlet": None,
            "village": None,
            "sub_district": None,
            "district": None,
            "province": None,
            "flagging_final": "GF",
            "field_assistant": "Chairunnisa Faza Nabillah",
            "supervisor": "Alfian Dwi Purnomo",
            "manager": "Anggi Yanuar Yanto",
            "region": "Region 3",
            "corr_tagging": "-7.992958,112.747986",
            "qa_spv": "Tonny Andhi Jaya",
            "qa_fi": "David Billy Jepryanto",
            "co_detasseling": "Nisa jep",
            "audit_date": datetime.date(2026, 5, 18),
            "audit_week": "21.0",
            "field_size_ha": decimal.Decimal("0.16"),
            "male_split": "Yes",
            "sowing_ratio": "05:02:00",
            "split_field": "No",
            "previous_crop": "Not Corn",
            "one_seed_hole": "Yes",
            "isolation_problem": "No",
            "crop_uniformity": "Fair",
            "crop_health": "Poor",
            "roguing_status": "On Going",
            "lsv_status": "Moderate",
            "offtype_m": "0.0",
            "offtype_f": ">0",
            "poi_accuracy": "Not Valid",
            "rev_planting_date": datetime.date(2026, 4, 24),
            "decision": "Pass with Note",
            "action_needed": "Roguing",
            "pld_reason": None,
            "flagging": "GF",
            "remarks": "-",
        }]

        def fake_run_query(sql, values=(), fetch_one=False):
            if "COUNT(*)" in sql:
                return {"total": 1}
            return mock_raw

        with patch.object(api, "run_query", side_effect=fake_run_query):
            res = api.list_field_audit_vegetative(field_number="DC6715080")

        self.assertEqual(res["total"], 1)
        self.assertEqual(len(res["items"]), 1)
        self.assertEqual(res["items"][0]["field_number"], "DC6715080")
        self.assertEqual(len(res["items"][0]), 50)

    def test_get_vegetative_by_field_number_and_id(self):
        mock_row = {col: None for col in api.VEGETATIVE_COLUMNS}
        mock_row["field_number"] = "DC6715080"
        mock_row["season"] = "DS26"

        with patch.object(api, "run_query", return_value=mock_row) as mock_query:
            result = api.get_field_audit_vegetative("DC6715080")
            self.assertEqual(result["field_number"], "DC6715080")
            self.assertIn("WHERE `field_number` = %s", mock_query.call_args[0][0])

        with patch.object(api, "run_query", return_value=mock_row) as mock_query:
            result = api.get_field_audit_vegetative("18855")
            self.assertEqual(result["field_number"], "DC6715080")
            self.assertIn("WHERE `id` = %s", mock_query.call_args[0][0])

    def test_get_vegetative_not_found_raises_404(self):
        with patch.object(api, "run_query", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                api.get_field_audit_vegetative("NON_EXISTING")
            self.assertEqual(ctx.exception.status_code, 404)

    def test_list_field_audit_with_phase_delegates_to_vegetative(self):
        with patch.object(api, "query_vegetative_items", return_value={"items": [], "total": 0, "limit": 100, "offset": 0}) as mock_veg:
            res = api.list_field_audit(phase="vegetative")
            mock_veg.assert_called_once()
            self.assertEqual(res["total"], 0)

    def test_get_field_audit_with_phase_delegates_to_vegetative(self):
        with patch.object(api, "fetch_field_audit_vegetative", return_value={"field_number": "F-01"}) as mock_fetch:
            res = api.get_field_audit(123, phase="fase-vegetative")
            mock_fetch.assert_called_once_with("123")
            self.assertEqual(res["field_number"], "F-01")


if __name__ == "__main__":
    unittest.main()
