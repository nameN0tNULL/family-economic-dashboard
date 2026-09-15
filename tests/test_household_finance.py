from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from family_economic_dashboard.household_finance import load_private_snapshots, snapshots_to_observations


class HouseholdFinanceTests(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".csv", delete=False)
        tmp.write(text)
        tmp.close()
        return Path(tmp.name)

    def test_private_snapshot_derives_safety_metrics_without_raw_amounts(self) -> None:
        path = self._write(
            "date,liquid_assets,after_tax_income,essential_expenses,debt_payments,total_expenses,stable_income_if_primary_lost,note\n"
            "2026-09-30,300000,50000,18000,12000,38000,16000,test\n"
        )
        rows = load_private_snapshots(path)
        obs = {r["indicator"]: r for r in snapshots_to_observations(rows)}
        self.assertAlmostEqual(obs["cash_runway_months"]["value"], 10.0)
        self.assertAlmostEqual(obs["debt_service_ratio"]["value"], 24.0)
        self.assertAlmostEqual(obs["household_savings_rate"]["value"], 24.0)
        self.assertAlmostEqual(obs["fixed_obligation_ratio"]["value"], 60.0)
        self.assertAlmostEqual(obs["primary_income_loss_runway_months"]["value"], 300000 / 14000)
        for row in obs.values():
            self.assertNotIn("300000", row["note"])
            self.assertNotIn("50000", row["note"])

    def test_stable_income_covering_mandatory_outflows_caps_stress_runway(self) -> None:
        path = self._write(
            "date,liquid_assets,after_tax_income,essential_expenses,debt_payments,total_expenses,stable_income_if_primary_lost,note\n"
            "2026-09-30,100000,30000,10000,5000,22000,16000,test\n"
        )
        obs = {r["indicator"]: r for r in snapshots_to_observations(load_private_snapshots(path))}
        self.assertEqual(obs["primary_income_loss_runway_months"]["value"], 120.0)

    def test_total_expenses_cannot_be_below_mandatory_outflows(self) -> None:
        path = self._write(
            "date,liquid_assets,after_tax_income,essential_expenses,debt_payments,total_expenses,stable_income_if_primary_lost,note\n"
            "2026-09-30,100000,30000,10000,5000,12000,5000,test\n"
        )
        with self.assertRaises(ValueError):
            load_private_snapshots(path)


if __name__ == "__main__":
    unittest.main()
