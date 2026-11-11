import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

import generative_api
import harvest_api
import pre_harvest_api
import vegetative_api


class OrderByApiTests(unittest.TestCase):
    def test_phase_list_queries_use_requested_order(self):
        query_functions = (
            vegetative_api.query_vegetative_items,
            generative_api.query_generative_items,
            pre_harvest_api.query_preharvest_items,
            harvest_api.query_harvest_items,
        )
        for query_function in query_functions:
            with self.subTest(query_function=query_function.__name__):
                run_query = MagicMock(side_effect=[{"total": 0}, []])

                query_function(
                    run_query_fn=run_query,
                    table_name="field_audits",
                    order_by="season",
                    order="asc",
                )

                list_sql = run_query.call_args_list[1].args[0]
                self.assertIn("ORDER BY `season` ASC", list_sql)

    def test_phase_list_queries_exclude_pld_rows_from_items_and_total(self):
        query_functions = (
            vegetative_api.query_vegetative_items,
            generative_api.query_generative_items,
            pre_harvest_api.query_preharvest_items,
            harvest_api.query_harvest_items,
        )
        for query_function in query_functions:
            with self.subTest(query_function=query_function.__name__):
                run_query = MagicMock(side_effect=[{"total": 0}, []])

                query_function(run_query_fn=run_query, table_name="field_audits")

                for call in run_query.call_args_list:
                    self.assertIn("`flagging_final` <> %s", call.args[0])
                    self.assertIn("PLD", call.args[1])

    def test_phase_detail_queries_exclude_pld_rows_for_id_and_field_number(self):
        fetch_functions = (
            vegetative_api.fetch_field_audit_vegetative,
            generative_api.fetch_field_audit_generative,
            pre_harvest_api.fetch_field_audit_preharvest,
            harvest_api.fetch_field_audit_harvest,
        )
        for fetch_function in fetch_functions:
            with self.subTest(fetch_function=fetch_function.__name__):
                run_query = MagicMock(side_effect=[None, {"field_number": "123"}])

                fetch_function(
                    identifier="123",
                    run_query_fn=run_query,
                    table_name="field_audits",
                )

                self.assertEqual(run_query.call_count, 2)
                for call in run_query.call_args_list:
                    self.assertIn("`flagging_final` <> %s", call.args[0])
                    self.assertEqual(call.args[1][-1], "PLD")

    def test_invalid_order_by_is_rejected_before_query(self):
        run_query = MagicMock()

        with self.assertRaises(HTTPException) as raised:
            pre_harvest_api.query_preharvest_items(
                run_query_fn=run_query,
                table_name="field_audits",
                order_by="id; DROP TABLE field_audits",
            )

        self.assertEqual(raised.exception.status_code, 422)
        run_query.assert_not_called()

    def test_invalid_order_direction_is_rejected_before_query(self):
        run_query = MagicMock()

        with self.assertRaises(HTTPException) as raised:
            harvest_api.query_harvest_items(
                run_query_fn=run_query,
                table_name="field_audits",
                order="sideways",
            )

        self.assertEqual(raised.exception.status_code, 422)
        run_query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
