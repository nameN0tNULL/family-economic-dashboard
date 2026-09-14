import unittest
from pathlib import Path
from family_economic_dashboard.engine import calculate_dashboard, load_config, load_observations

ROOT = Path(__file__).resolve().parents[1]


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config/indicators.json")
        cls.data = load_observations(ROOT / "data/observations.csv")
        cls.result = calculate_dashboard(cls.config, cls.data, "2026-09-01")

    def test_build_dashboard_has_all_dimensions(self):
        self.assertEqual(len(self.result.dimensions), 5)
        self.assertEqual(len(self.result.indicators), 16)
        self.assertTrue(0 <= self.result.overall_score <= 100)

    def test_cash_runway_absolute_rule_is_green(self):
        row = next(r for r in self.result.indicators if r["indicator"] == "cash_runway_months")
        self.assertEqual(row["status"], "green")

    def test_longer_home_sale_cycle_can_trigger_warning(self):
        row = next(r for r in self.result.indicators if r["indicator"] == "home_days_on_market")
        self.assertIn(row["status"], {"yellow", "red"})


if __name__ == "__main__":
    unittest.main()
