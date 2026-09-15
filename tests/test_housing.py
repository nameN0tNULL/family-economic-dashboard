from __future__ import annotations

import unittest
from datetime import date

from family_economic_dashboard.collect_housing import parse_70_city_prices
from family_economic_dashboard.housing import summarize_housing


class HousingTests(unittest.TestCase):
    def test_parse_70_city_price_tables(self) -> None:
        cities = [f"城{i}" for i in range(70)]
        def table(mom: float, yoy: float, avg: float) -> str:
            rows = []
            for i in range(35):
                a, b = cities[i], cities[i + 35]
                rows.append(
                    f"<tr><td>{a}</td><td>{100+mom}</td><td>{100+yoy}</td><td>{100+avg}</td>"
                    f"<td>{b}</td><td>{100+mom}</td><td>{100+yoy}</td><td>{100+avg}</td></tr>"
                )
            return "<table>" + "".join(rows) + "</table>"
        html = table(-0.2, -2.3, -2.0) + table(-0.1, -3.5, -4.0)
        parsed = parse_70_city_prices(html)
        self.assertEqual(len(parsed["new"]), 70)
        self.assertEqual(len(parsed["second_hand"]), 70)
        self.assertAlmostEqual(parsed["new"][0][1], -0.2)
        self.assertAlmostEqual(parsed["second_hand"][0][2], -3.5)

    def test_gba_sample_is_explicit_and_second_hand_can_turn_red(self) -> None:
        rows = []
        for city in ("广州", "深圳", "惠州"):
            rows.append({
                "date": date(2026, 8, 31), "city": city, "market": "new",
                "mom_pct": -0.1, "yoy_pct": -2.0, "ytd_avg_pct": -2.5, "source_url": "u",
            })
            rows.append({
                "date": date(2026, 8, 31), "city": city, "market": "second_hand",
                "mom_pct": -0.3, "yoy_pct": -6.0, "ytd_avg_pct": -7.0, "source_url": "u",
            })
        summary = summarize_housing(rows)
        gba_used = next(
            r for r in summary["summaries"]
            if r["cluster"] == "greater_bay_area" and r["market"] == "second_hand"
        )
        self.assertEqual(gba_used["scope"], "70_city_sample")
        self.assertEqual(gba_used["expected_cities"], 3)
        self.assertEqual(gba_used["status"], "red")


if __name__ == "__main__":
    unittest.main()
