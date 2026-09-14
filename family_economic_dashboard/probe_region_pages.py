from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

USER_AGENT = "family-economic-dashboard/1.0 (+GitHub Actions; regional official-source validation)"
SPACE_RE = re.compile(r"\s+")


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    @property
    def text(self) -> str:
        return SPACE_RE.sub(" ", "".join(self.parts).replace("\xa0", " ")).strip()


def fetch_text(url: str, timeout: int = 30) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset()
    for encoding in (charset, "utf-8", "gb18030"):
        if not encoding:
            continue
        try:
            html = raw.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            pass
    else:
        html = raw.decode("utf-8", errors="replace")
    parser = TextParser()
    parser.feed(html)
    return parser.text


def signed(direction: str, number: str) -> float:
    value = float(number)
    return -value if direction in {"下降", "减少", "下跌"} else value


def pct(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        if len(m.groups()) == 1:
            return float(m.group(1))
        return signed(m.group(1), m.group(2))
    return None


SOURCES = [
    {
        "region": "北京",
        "cluster": "jing_jin_ji",
        "kind": "current_release",
        "url": "https://tjj.beijing.gov.cn/tjsj_31433/sjjd_31444/202608/t20260818_4826859.html",
        "metrics": {
            "industrial_growth": [r"规模以上工业增加值[^。]{0,40}?同比(增长|下降)([0-9.]+)%"],
            "fixed_asset_investment_growth": [r"固定资产投资（不含农户）同比(增长|下降)([0-9.]+)%"],
            "retail_sales_growth": [r"社会消费品零售总额[0-9.]+亿元，(增长|下降)([0-9.]+)%"],
        },
    },
    {
        "region": "天津",
        "cluster": "jing_jin_ji",
        "kind": "current_release",
        "url": "https://www.tj.gov.cn/sq/zfsj/sjfb/202608/t20260820_7355185.html",
        "metrics": {
            "industrial_growth": [r"规模以上工业增加值[^。]{0,50}?(?:同比)?(增长|下降)([0-9.]+)%"],
            "fixed_asset_investment_growth": [r"固定资产投资[^。]{0,50}?(?:同比)?(增长|下降)([0-9.]+)%"],
            "retail_sales_growth": [r"社会消费品零售总额[^。]{0,60}?(?:同比)?(增长|下降)([0-9.]+)%"],
        },
    },
    {
        "region": "河北",
        "cluster": "jing_jin_ji",
        "kind": "index_reachability",
        "url": "https://tjj.hebei.gov.cn/",
        "metrics": {},
    },
    {
        "region": "上海",
        "cluster": "yangtze_river_delta",
        "kind": "industrial_release",
        "url": "https://tjj.sh.gov.cn/sjxx/20260813/b3771ac855a246a4b2d47786c37f4b25.html",
        "metrics": {
            "industrial_output_growth": [r"工业总产值[0-9.]+亿元，比去年同期(增长|下降)([0-9.]+)%"],
        },
    },
    {
        "region": "上海",
        "cluster": "yangtze_river_delta",
        "kind": "investment_release",
        "url": "https://tjj.sh.gov.cn/sjxx/20260817/150e0926688d4e94bb631e12fcbb030a.html",
        "metrics": {
            "fixed_asset_investment_growth": [r"全社会固定资产投资比去年同期(增长|下降)([0-9.]+)%"],
        },
    },
    {
        "region": "上海",
        "cluster": "yangtze_river_delta",
        "kind": "retail_release",
        "url": "https://tjj.sh.gov.cn/ydsj51/20260814/0e4a771b6d0b4d8f99f99d9c9cf4a65a.html",
        "metrics": {
            "retail_sales_growth": [
                r"社会消费品零售总额[^%]{0,180}?1-7月[^%]{0,180}?([+-]?[0-9.]+)"
            ],
        },
    },
    {
        "region": "江苏",
        "cluster": "yangtze_river_delta",
        "kind": "current_release",
        "url": "https://tj.jiangsu.gov.cn/art/2026/8/24/art_85275_11819992.html",
        "metrics": {
            "industrial_growth": [r"规模以上工业增加值同比(增长|下降)([0-9.]+)%"],
            "fixed_asset_investment_growth": [r"固定资产投资同比(增长|下降)([0-9.]+)%"],
            "retail_sales_growth": [r"社会消费品零售总额[0-9.]+亿元，同比(增长|下降)([0-9.]+)%"],
        },
    },
    {
        "region": "浙江",
        "cluster": "yangtze_river_delta",
        "kind": "index_reachability",
        "url": "https://tjj.zj.gov.cn/col/col1525492/index.html",
        "metrics": {},
    },
    {
        "region": "安徽",
        "cluster": "yangtze_river_delta",
        "kind": "index_reachability",
        "url": "https://tjj.ah.gov.cn/",
        "metrics": {},
    },
]


def main() -> None:
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    checks: list[dict] = []
    rows: list[dict[str, str]] = []
    accessible_regions: set[str] = set()

    for source in SOURCES:
        region = source["region"]
        url = source["url"]
        try:
            text = fetch_text(url)
            accessible_regions.add(region)
            parsed: dict[str, float] = {}
            for indicator, patterns in source["metrics"].items():
                value = pct(text, patterns)
                if value is not None:
                    parsed[indicator] = value
                    rows.append(
                        {
                            "period": "2026-07",
                            "cluster": source["cluster"],
                            "region": region,
                            "indicator": indicator,
                            "value": f"{value:g}",
                            "source_url": url,
                            "collected_at": collected_at,
                        }
                    )
            checks.append(
                {
                    "region": region,
                    "cluster": source["cluster"],
                    "kind": source["kind"],
                    "url": url,
                    "status": "ok",
                    "text_length": len(text),
                    "metrics_expected": sorted(source["metrics"]),
                    "metrics_parsed": parsed,
                    "sample": text[:220],
                }
            )
            print(f"[ok] {region} {source['kind']}: chars={len(text)} parsed={parsed}")
        except Exception as exc:
            checks.append(
                {
                    "region": region,
                    "cluster": source["cluster"],
                    "kind": source["kind"],
                    "url": url,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[warn] {region} {source['kind']}: {type(exc).__name__}: {exc}")

    Path("data").mkdir(exist_ok=True)
    out_csv = Path("data/region_page_probe.csv")
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["period", "cluster", "region", "indicator", "value", "source_url", "collected_at"],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "collected_at": collected_at,
        "purpose": "GitHub Hosted Runner reachability and parser validation for regional official sources",
        "accessible_region_count": len(accessible_regions),
        "accessible_regions": sorted(accessible_regions),
        "metric_row_count": len(rows),
        "checks": checks,
    }
    Path("data/region_page_probe_provenance.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not accessible_regions:
        raise SystemExit("No provincial official source was accessible")
    print(f"Provincial page probe complete: regions={len(accessible_regions)}, metric_rows={len(rows)}")


if __name__ == "__main__":
    main()
