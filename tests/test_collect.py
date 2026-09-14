import unittest
from family_economic_dashboard.collect import parse_page, extract_signed_pct, amount_to_yi


class CollectorParserTests(unittest.TestCase):
    def test_html_link_parser(self):
        p = parse_page('<a href="/x">2026年1—7月份全国规模以上工业企业利润增长17.6%</a>')
        self.assertEqual(p.links[0][0], "/x")
        self.assertIn("工业企业利润", p.links[0][1])

    def test_signed_percent(self):
        text = "民间投资同比下降9.4%；扣除房地产开发的民间投资下降5.7%。"
        self.assertEqual(extract_signed_pct(text, r"民间投资同比(增长|下降)([0-9.]+)%"), -9.4)

    def test_loan_unit_conversion(self):
        self.assertEqual(amount_to_yi("增加", "1.19", "万亿元"), 11900.0)
        self.assertEqual(amount_to_yi("减少", "800", "亿元"), -800.0)


if __name__ == "__main__":
    unittest.main()
