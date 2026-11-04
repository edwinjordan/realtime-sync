import datetime
import decimal
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException
import vegetative_api


class VegetativeApiModuleTests(unittest.TestCase):
    def test_normalize_pagination_parses_defaults_and_strings(self):
        self.assertEqual(vegetative_api.normalize_pagination(50, 10), (50, 10))
        self.assertEqual(vegetative_api.normalize_pagination("25", "5"), (25, 5))
        self.assertEqual(vegetative_api.normalize_pagination(None, "invalid"), (100, 0))

    def test_format_vegetative_row_handles_various_types(self):
        raw = {
            "season": "DS26",
            "actual_area_planted": decimal.Decimal("0.16"),
            "discard_area_ha": decimal.Decimal("0.00"),
            "audit_date": datetime.date(2026, 5, 18),
            "planting_ratio": datetime.time(4, 2),
            "split_planting": datetime.timedelta(seconds=3665),
            "remarks": "-",
            "extra_column": "ignored",
        }
        res = vegetative_api.format_vegetative_row(raw)
        self.assertEqual(len(res), len(vegetative_api.VEGETATIVE_COLUMNS))
        self.assertEqual(res["actual_area_planted"], 0.16)
        self.assertEqual(res["discard_area_ha"], 0)
        self.assertEqual(res["audit_date"], "2026-05-18")
        self.assertEqual(res["planting_ratio"], "04:02:00")
        self.assertEqual(res["split_planting"], "01:01:05")
        self.assertEqual(res["remarks"], "-")
        self.assertNotIn("extra_column", res)

    def test_query_vegetative_items_uses_custom_executor(self):
        fake_run_query = MagicMock(side_effect=[
            {"total": 1},
            [{"season": "DS26", "field_number": "DC6715080"}],
        ])
        result = vegetative_api.query_vegetative_items(
            limit=10,
            offset=0,
            filters_dict={"season": "DS26"},
            run_query_fn=fake_run_query,
            table_name="custom_table",
        )
        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["season"], "DS26")
        self.assertIn("FROM `custom_table`", fake_run_query.call_args_list[0][0][0])

    def test_fetch_field_audit_vegetative_not_found(self):
        fake_run_query = MagicMock(return_value=None)
        with self.assertRaises(HTTPException) as ctx:
            vegetative_api.fetch_field_audit_vegetative(
                identifier="NOT_FOUND",
                run_query_fn=fake_run_query,
                table_name="custom_table",
            )
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()

