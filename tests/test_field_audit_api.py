import datetime
import decimal
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.routing import Match

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
            "name": "field_audits",
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
        api.TABLE_NAME = "field_audits"

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


class FieldAuditRouteTests(unittest.TestCase):
    def test_main_list_query_uses_requested_order(self):
        original_table_name = api.TABLE_NAME
        api.TABLE_NAME = "field_audits"
        try:
            with patch.object(
                api,
                "run_query",
                side_effect=[{"total": 0}, []],
            ) as run_query:
                api.list_field_audit(
                    limit=10,
                    offset=0,
                    phase=None,
                    fase=None,
                    order_by="season",
                    order="asc",
                )
        finally:
            api.TABLE_NAME = original_table_name

        list_sql = run_query.call_args_list[1].args[0]
        self.assertIn("ORDER BY `season` ASC", list_sql)
        for call in run_query.call_args_list:
            self.assertIn("`flagging_final` <> %s", call.args[0])
            self.assertIn("PLD", call.args[1])

    def test_main_detail_query_excludes_pld_rows(self):
        original_table_name = api.TABLE_NAME
        api.TABLE_NAME = "field_audits"
        try:
            with patch.object(api, "run_query", return_value={"id": 123}) as run_query:
                api.get_field_audit(123, phase=None, fase=None)
        finally:
            api.TABLE_NAME = original_table_name

        self.assertIn("`flagging_final` <> %s", run_query.call_args.args[0])
        self.assertEqual(run_query.call_args.args[1], (123, "PLD"))

    def test_row_id_route_only_matches_integer_paths(self):
        route = next(
            route
            for route in api.app.routes
            if getattr(route, "endpoint", None) is api.get_field_audit
        )

        def match(path):
            return route.matches(
                {
                    "type": "http",
                    "path": path,
                    "method": "GET",
                    "root_path": "",
                    "headers": [],
                }
            )[0]

        self.assertEqual(match("/api/field-audit/preharvest"), Match.NONE)
        self.assertEqual(match("/api/field-audit/123"), Match.FULL)


class WindowsEventLoopPolicyTests(unittest.TestCase):
    @unittest.skipUnless(api.os.name == "nt", "Windows event loop policy is Windows-only")
    def test_api_uses_selector_event_loop_policy_on_windows(self):
        api._configure_windows_event_loop_policy()

        self.assertIsInstance(
            api.asyncio.get_event_loop_policy(),
            api.asyncio.WindowsSelectorEventLoopPolicy,
        )
        loop = api.asyncio.new_event_loop()
        try:
            self.assertIsInstance(loop, api.asyncio.SelectorEventLoop)
        finally:
            loop.close()

    def test_lifespan_suppresses_only_expected_proactor_reset(self):
        async def verify_exception_handler():
            loop = api.asyncio.get_running_loop()
            delegated_contexts = []
            previous_handler = lambda event_loop, context: delegated_contexts.append(
                (event_loop, context)
            )
            loop.set_exception_handler(previous_handler)

            async with api.app.router.lifespan_context(api.app):
                handler = loop.get_exception_handler()
                self.assertIsNotNone(handler)

                expected_context = {
                    "message": api._PROACTOR_CONNECTION_LOST_MESSAGE,
                    "exception": ConnectionResetError(10054, "connection reset"),
                }
                handler(loop, expected_context)
                self.assertEqual(delegated_contexts, [])

                unexpected_context = {
                    "message": "another callback failed",
                    "exception": ConnectionResetError(10054, "connection reset"),
                }
                handler(loop, unexpected_context)
                wrong_exception_context = {
                    "message": api._PROACTOR_CONNECTION_LOST_MESSAGE,
                    "exception": RuntimeError("unexpected exception type"),
                }
                handler(loop, wrong_exception_context)
                self.assertEqual(
                    delegated_contexts,
                    [(loop, unexpected_context), (loop, wrong_exception_context)],
                )

            self.assertIs(loop.get_exception_handler(), previous_handler)
            loop.set_exception_handler(None)

        api.asyncio.run(verify_exception_handler())


if __name__ == "__main__":
    unittest.main()
