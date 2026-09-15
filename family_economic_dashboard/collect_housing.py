from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from .collect import Observation, discover_article, fetch_html, parse_page, period_end, write_observations


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _city(value: str) -> str:
    return re.sub(r"\s+", "", _clean(value))


def _number(value: str) -> float | None:
    value = _clean(value).replace("%", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", value):
        return None
    return float(value)


def _looks_like_city(value: str) -> bool:
    compact = _city(value)
    return bool(compact and re.search(r"[\u4e00-\u9fff]", compact) and not re.search(r"\d", compact) and compact not in {"城市", "环比", "同比"})


def _table_price_rows(table: list[list[str]]) -> list[tuple[str, float, float, float]]:
    rows: list[tuple[str, float, float, float]] = []
    seen: set[str] = set()
    for raw in table:
        cells = [_clean(x) for x in raw]
        # The first two NBS price tables are two 4-column city blocks side by side.
        for offset in (0, 4):
            if len(cells) < offset + 4 or not _looks_like_city(cells[offset]):
                continue
            nums = [_number(cells[offset + i]) for i in (1, 2, 3)]
            if any(x is None for x in nums):
                continue
            city = _city(cells[offset])
            if city in seen:
                continue
            seen.add(city)
            mom, yoy, avg = (float(x) for x in nums if x is not None)
            rows.append((city, mom - 100.0, yoy - 100.0, avg - 100.0))
    return rows


def parse_70_city_prices(html_text: str) -> dict[str, list[tuple[str, float, float, float]]]:
    parser = TableParser()
    parser.feed(html_text)
    candidates = []
    for table in parser.tables:
        parsed = _table_price_rows(table)
        if len(parsed) >= 65:
            candidates.append(parsed)
    if len(candidates) < 2:
        raise ValueError(f"Expected at least two 70-city price tables, got {len(candidates)}")
    new_rows, second_rows = candidates[0], candidates[1]
    if len(new_rows) != 70 or len(second_rows) != 70:
        raise ValueError(f"Unexpected city counts: new={len(new_rows)}, second_hand={len(second_rows)}")
    return {"new": new_rows, "second_hand": second_rows}


def _signed_pct(text: str, pattern: str) -> float:
    m = re.search(pattern, text)
    if not m:
        raise ValueError(f"Pattern did not match: {pattern}")
    value = float(m.group(2))
    return -value if m.group(1) in {"下降", "减少", "下跌"} else value


def collect_macro(nbs_index: str) -> tuple[list[Observation], dict[str, Any]]:
    url, title = discover_article(nbs_index, lambda t: "全国房地产市场基本情况" in t)
    text = parse_page(fetch_html(url)).text
    d = period_end(title, text)
    observations = [
        Observation(d, "national_real_estate_investment_yoy", _signed_pct(text, r"全国房地产开发投资[0-9.]+亿元，同比(增长|下降)([0-9.]+)%"), f"{title}；全国房地产开发投资累计同比", url),
        Observation(d, "national_new_home_sales_area_yoy", _signed_pct(text, r"新建商品房销售面积[0-9.]+万平方米，同比(增长|下降)([0-9.]+)%"), f"{title}；新建商品房销售面积累计同比", url),
        Observation(d, "national_second_hand_net_sign_area_yoy", _signed_pct(text, r"二手房交易网签面积[^。；]*?同比(增长|下降)([0-9.]+)%"), f"{title}；住建部口径二手房交易网签面积累计同比", url),
        Observation(d, "national_developer_funding_yoy", _signed_pct(text, r"房地产开发企业到位资金[0-9.]+亿元，同比(增长|下降)([0-9.]+)%"), f"{title}；房地产开发企业到位资金累计同比", url),
    ]
    return observations, {
        "source": "国家统计局-全国房地产市场基本情况",
        "title": title,
        "url": url,
        "period": d.isoformat(),
        "indicators": {o.indicator: o.value for o in observations},
    }


def collect_city_prices(nbs_index: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    url, title = discover_article(nbs_index, lambda t: "70个大中城市" in t and "商品住宅销售价格变动情况" in t)
    html_text = fetch_html(url)
    text = parse_page(html_text).text
    d = period_end(title, text)
    parsed = parse_70_city_prices(html_text)
    rows: list[dict[str, Any]] = []
    for market, items in parsed.items():
        for city, mom, yoy, avg in items:
            rows.append({
                "date": d.isoformat(),
                "city": city,
                "market": market,
                "mom_pct": round(mom, 4),
                "yoy_pct": round(yoy, 4),
                "ytd_avg_pct": round(avg, 4),
                "source_url": url,
            })
    return rows, {
        "source": "国家统计局-70个大中城市商品住宅销售价格",
        "title": title,
        "url": url,
        "period": d.isoformat(),
        "city_count": len({r["city"] for r in rows}),
        "row_count": len(rows),
        "markets": {market: len(items) for market, items in parsed.items()},
    }


def write_city_prices(path: Path, new_rows: list[dict[str, Any]]) -> None:
    existing: list[dict[str, str]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", newline="") as f:
            existing = [dict(row) for row in csv.DictReader(f)]
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in existing + new_rows:
        if row.get("date") and row.get("city") and row.get("market"):
            merged[(str(row["date"]), str(row["city"]), str(row["market"]))] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["date", "city", "market", "mom_pct", "yoy_pct", "ytd_avg_pct", "source_url"]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect NBS housing and 70-city price statistics")
    parser.add_argument("--sources", default="config/sources.json")
    parser.add_argument("--city-output", default="data/housing_city_prices.csv")
    parser.add_argument("--observation-output", default="data/housing_observations.csv")
    parser.add_argument("--provenance", default="data/housing_provenance.json")
    args = parser.parse_args()

    cfg = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    nbs_index = cfg["nbs_index"]
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    city_rows, city_meta = collect_city_prices(nbs_index)
    observations, macro_meta = collect_macro(nbs_index)
    if len(city_rows) != 140:
        raise SystemExit(f"Refusing to write incomplete 70-city snapshot: {len(city_rows)} rows")

    write_city_prices(Path(args.city_output), city_rows)
    write_observations(Path(args.observation_output), observations, collected_at)
    provenance = {
        "collected_at": collected_at,
        "sources": [city_meta, macro_meta],
        "notes": [
            "City price changes are converted from official index levels: 99.8 -> -0.2% and 103.0 -> +3.0%.",
            "Economic-group views are explicitly 70-city samples, not complete metropolitan-area coverage.",
            "Second-hand transaction area is Ministry of Housing and Urban-Rural Development data quoted by NBS.",
        ],
    }
    Path(args.provenance).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Collected housing: city_rows={len(city_rows)}, cities={city_meta['city_count']}, "
        + ", ".join(f"{o.indicator}={o.value:g}" for o in observations)
    )


if __name__ == "__main__":
    main()
