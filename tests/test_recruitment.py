from datetime import date
import unittest

from family_economic_dashboard.recruitment import search_snapshots_to_observations, summarize_recruitment


class RecruitmentTests(unittest.TestCase):
    def test_market_summary_tracks_salary_breadth(self):
        market = [
            {"scope": "京津冀", "period_end": date(2025, 12, 31), "job": "A", "salary_wan_month": 1.0, "source_url": ""},
            {"scope": "京津冀", "period_end": date(2025, 12, 31), "job": "B", "salary_wan_month": 2.0, "source_url": ""},
            {"scope": "京津冀", "period_end": date(2026, 3, 31), "job": "A", "salary_wan_month": 0.9, "source_url": ""},
            {"scope": "京津冀", "period_end": date(2026, 3, 31), "job": "B", "salary_wan_month": 2.2, "source_url": ""},
        ]
        result = summarize_recruitment(market, [])
        row = result["market_summaries"][0]
        self.assertEqual(row["hot_job_count"], 2)
        self.assertEqual(row["up_count"], 1)
        self.assertEqual(row["down_count"], 1)
        self.assertAlmostEqual(row["median_salary_k"], 15.5)

    def test_search_basket_generates_core_observations(self):
        rows = [
            {"date": date(2026, 9, 1), "platform": "BOSS", "city": "上海", "keyword": "Java", "result_count": 100.0, "salary_median_k": 25.0, "source_url": "", "note": ""},
            {"date": date(2026, 9, 1), "platform": "猎聘", "city": "上海", "keyword": "Java", "result_count": 80.0, "salary_median_k": 27.0, "source_url": "", "note": ""},
        ]
        observations = search_snapshots_to_observations(rows)
        values = {r["indicator"]: r["value"] for r in observations}
        self.assertEqual(values["job_postings"], 90.0)
        self.assertEqual(values["salary_mid"], 26.0)


if __name__ == "__main__":
    unittest.main()
