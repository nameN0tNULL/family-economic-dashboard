import unittest
from datetime import date
from pathlib import Path
from family_economic_dashboard.engine import calculate_dashboard, load_config

ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config/indicators.json")

    def test_missing_metrics_do_not_create_fake_neutral_score(self):
        result = calculate_dashboard(self.config, [], date(2026, 9, 1))
        self.assertIsNone(result.overall_score)
        self.assertEqual(result.overall_status, "unknown")
        self.assertEqual(result.overall_coverage, 0.0)

    def test_direct_official_growth_rate_is_scored_as_absolute_value(self):
        obs = [{"date": date(2026, 7, 31), "indicator": "private_investment", "value": -9.4, "note": "", "source_url": ""}]
        result = calculate_dashboard(self.config, obs, date(2026, 7, 31))
        row = next(r for r in result.indicators if r["indicator"] == "private_investment")
        self.assertEqual(row["status"], "yellow")

    def test_family_absolute_rule_still_works(self):
        obs = [{"date": date(2026, 9, 1), "indicator": "cash_runway_months", "value": 5.5, "note": "", "source_url": ""}]
        result = calculate_dashboard(self.config, obs, date(2026, 9, 1))
        row = next(r for r in result.indicators if r["indicator"] == "cash_runway_months")
        self.assertEqual(row["status"], "red")


if __name__ == "__main__":
    unittest.main()
