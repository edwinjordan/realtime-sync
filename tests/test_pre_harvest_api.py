import unittest
from unittest.mock import MagicMock

import pre_harvest_api


class PreHarvestApiTests(unittest.TestCase):
    def test_preharvest_query_selects_distinct_columns(self):
        fake_run_query = MagicMock(
            side_effect=[
                {"total": 0},
                [],
            ]
        )

        pre_harvest_api.query_preharvest_items(
            run_query_fn=fake_run_query,
            table_name="field_audit",
        )

        select_sql = fake_run_query.call_args_list[1].args[0]
        self.assertIn("`pre_harvest_male_chopping_rows`", select_sql)
        self.assertIn("`pre_harvest_crop_health`", select_sql)
        self.assertNotIn(
            "`pre_harvest_male_chopping_rowspre_harvest_crop_health`",
            select_sql,
        )
        self.assertEqual(
            len(pre_harvest_api.PREHARVEST_COLUMNS),
            len(set(pre_harvest_api.PREHARVEST_COLUMNS)),
        )


if __name__ == "__main__":
    unittest.main()
