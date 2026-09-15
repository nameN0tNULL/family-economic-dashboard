from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}

CLUSTERS = {
    "jing_jin_ji": {
        "name": "京津冀",
        "scope": "exact",
        "expected_regions": 3,
        "note": "北京、天津、河北三省市。",
    },
    "yangtze_river_delta": {
        "name": "长三角",
        "scope": "exact",
        "expected_regions": 4,
        "note": "上海、江苏、浙江、安徽四省市。",
    },
    "greater_bay_area_proxy": {
        "name": "粤港澳大湾区（广东省代理）",
        "scope": "proxy",
        "expected_regions": 1,
        "note": "当前月度工业/投资使用广东全省做代理，不等同于大湾区9市+香港+澳门精确口径。",
    },
    "chengdu_chongqing_proxy": {
        "name": "成渝地区（川渝代理）",
        "scope": "proxy",
        "expected_regions": 2,
        "note": "当前使用四川全省+重庆市做代理，范围大于成渝地区双城经济圈官方精确口径。",
    },
    "middle_yangtze_proxy": {
        "name": "长江中游（鄂湘赣代理）",
        "scope": "proxy",
        "expected_regions": 3,
        "note": "当前使用湖北、湖南、江西三省做代理，范围大于长江中游城市群官方精确口径。",
    },
}

INDICATORS = {
    "industrial_growth": "规上工业增加值累计增长",
    "fixed_asset_investment_growth": "固定资产投资累计增长",
}


def load_regional_observations(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            try:
                value = float(raw["value"])
                d = date.fromisoformat(raw["date"])
            except (KeyError, TypeError, ValueError):
                continue
            row = dict(raw)
            row["value"] = value
            row["date"] = d
            rows.append(row)
    return rows


def _status(negative_count: int, observed: int, deteriorating_count: int, comparable: int) -> str:
    if observed <= 0:
        return "unknown"
    negative_share = negative_count / observed
    deteriorating_share = deteriorating_count / comparable if comparable else 0.0
    if negative_share >= 2 / 3:
        return "red"
    if negative_count > 0 or deteriorating_share >= 2 / 3:
        return "yellow"
    return "green"


def summarize_regions(rows: list[dict]) -> dict:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        cluster = row.get("cluster", "")
        indicator = row.get("indicator", "")
        if cluster in CLUSTERS and indicator in INDICATORS:
            grouped[(cluster, indicator)].append(row)

    summaries: list[dict] = []
    latest_rows: list[dict] = []

    for cluster in CLUSTERS:
        for indicator in INDICATORS:
            items = grouped.get((cluster, indicator), [])
            if not items:
                continue
            dates = sorted({r["date"] for r in items})
            latest_date = dates[-1]
            previous_date = dates[-2] if len(dates) >= 2 else None
            latest = {r["region_code"]: r for r in items if r["date"] == latest_date}
            previous = {r["region_code"]: r for r in items if previous_date and r["date"] == previous_date}

            positives = sum(1 for r in latest.values() if r["value"] > 0)
            negatives = sum(1 for r in latest.values() if r["value"] < 0)
            zeros = sum(1 for r in latest.values() if r["value"] == 0)
            comparable_codes = sorted(set(latest) & set(previous))
            improving = sum(1 for code in comparable_codes if latest[code]["value"] > previous[code]["value"])
            deteriorating = sum(1 for code in comparable_codes if latest[code]["value"] < previous[code]["value"])
            unchanged = len(comparable_codes) - improving - deteriorating
            observed = len(latest)
            cluster_meta = CLUSTERS[cluster]
            expected = int(cluster_meta["expected_regions"])
            values = [r["value"] for r in latest.values()]
            status = _status(negatives, observed, deteriorating, len(comparable_codes))

            summaries.append(
                {
                    "cluster": cluster,
                    "cluster_name": cluster_meta["name"],
                    "scope": cluster_meta["scope"],
                    "scope_note": cluster_meta["note"],
                    "indicator": indicator,
                    "indicator_name": INDICATORS[indicator],
                    "latest_date": latest_date,
                    "previous_date": previous_date,
                    "median_growth": statistics.median(values) if values else None,
                    "min_growth": min(values) if values else None,
                    "max_growth": max(values) if values else None,
                    "positive_count": positives,
                    "negative_count": negatives,
                    "zero_count": zeros,
                    "improving_count": improving,
                    "deteriorating_count": deteriorating,
                    "unchanged_count": unchanged,
                    "comparable_count": len(comparable_codes),
                    "observed_regions": observed,
                    "expected_regions": expected,
                    "coverage": (100.0 * observed / expected) if expected else 0.0,
                    "status": status,
                    "status_icon": STATUS_ICON[status],
                }
            )

            for code, row in sorted(latest.items(), key=lambda kv: kv[1]["region"]):
                previous_value = previous.get(code, {}).get("value") if code in previous else None
                delta = row["value"] - previous_value if previous_value is not None else None
                latest_rows.append(
                    {
                        "cluster": cluster,
                        "cluster_name": cluster_meta["name"],
                        "scope": cluster_meta["scope"],
                        "indicator": indicator,
                        "indicator_name": INDICATORS[indicator],
                        "region": row["region"],
                        "region_code": code,
                        "date": latest_date,
                        "value": row["value"],
                        "previous_date": previous_date,
                        "previous_value": previous_value,
                        "delta_pp": delta,
                        "source": row.get("source", ""),
                        "source_url": row.get("source_url", ""),
                    }
                )

    summaries.sort(key=lambda r: (list(CLUSTERS).index(r["cluster"]), list(INDICATORS).index(r["indicator"])))
    latest_rows.sort(key=lambda r: (list(CLUSTERS).index(r["cluster"]), list(INDICATORS).index(r["indicator"]), r["region"]))
    return {"summaries": summaries, "latest_rows": latest_rows, "clusters": CLUSTERS}
