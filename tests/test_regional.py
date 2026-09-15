import unittest
from datetime import date

from family_economic_dashboard.regional import summarize_regions


class RegionalSummaryTests(unittest.TestCase):
    def test_diffusion_and_momentum(self):
        rows = [
            {"date": date(2026, 6, 30), "cluster": "jing_jin_ji", "region": "北京市", "region_code": "11", "indicator": "industrial_growth", "value": 3.4},
            {"date": date(2026, 6, 30), "cluster": "jing_jin_ji", "region": "天津市", "region_code": "12", "indicator": "industrial_growth", "value": 4.4},
            {"date": date(2026, 6, 30), "cluster": "jing_jin_ji", "region": "河北省", "region_code": "13", "indicator": "industrial_growth", "value": 6.1},
            {"date": date(2026, 7, 31), "cluster": "jing_jin_ji", "region": "北京市", "region_code": "11", "indicator": "industrial_growth", "value": 4.7},
            {"date": date(2026, 7, 31), "cluster": "jing_jin_ji", "region": "天津市", "region_code": "12", "indicator": "industrial_growth", "value": 4.0},
            {"date": date(2026, 7, 31), "cluster": "jing_jin_ji", "region": "河北省", "region_code": "13", "indicator": "industrial_growth", "value": 5.5},
        ]
        result = summarize_regions(rows)
        summary = result["summaries"][0]
        self.assertEqual(summary["positive_count"], 3)
        self.assertEqual(summary["negative_count"], 0)
        self.assertEqual(summary["improving_count"], 1)
        self.assertEqual(summary["deteriorating_count"], 2)
        self.assertEqual(summary["coverage"], 100.0)
        self.assertEqual(summary["status"], "yellow")

    def test_gba_is_explicit_proxy(self):
        rows = [
            {"date": date(2026, 7, 31), "cluster": "greater_bay_area_proxy", "region": "广东省", "region_code": "44", "indicator": "industrial_growth", "value": 3.0},
        ]
        result = summarize_regions(rows)
        summary = result["summaries"][0]
        self.assertEqual(summary["scope"], "proxy")
        self.assertIn("广东", summary["scope_note"])
        self.assertEqual(summary["coverage"], 100.0)


if __name__ == "__main__":
    unittest.main()
