from __future__ import annotations

import unittest

from family_economic_dashboard.city_vitality import summarize_city_population


class CityVitalityTests(unittest.TestCase):
    def test_population_diffusion_status(self) -> None:
        rows = [
            {"year": 2025, "cluster": "jing_jin_ji", "city": "北京", "resident_population_wan": 2180.0, "change_wan": -3.2, "change_pct": -0.15},
            {"year": 2025, "cluster": "jing_jin_ji", "city": "天津", "resident_population_wan": 1363.0, "change_wan": -1.0, "change_pct": -0.07},
            {"year": 2025, "cluster": "greater_bay_area", "city": "广州", "resident_population_wan": 1910.1, "change_wan": 12.3, "change_pct": 0.65},
            {"year": 2025, "cluster": "greater_bay_area", "city": "深圳", "resident_population_wan": 1824.85, "change_wan": 25.9, "change_pct": 1.44},
        ]
        result = summarize_city_population(rows)
        jjj = next(r for r in result["cluster_summaries"] if r["cluster"] == "jing_jin_ji")
        gba = next(r for r in result["cluster_summaries"] if r["cluster"] == "greater_bay_area")
        self.assertEqual(jjj["status"], "red")
        self.assertEqual(jjj["negative_count"], 2)
        self.assertEqual(gba["status"], "green")
        self.assertEqual(gba["positive_count"], 2)


if __name__ == "__main__":
    unittest.main()
