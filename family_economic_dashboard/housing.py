from __future__ import annotations

import csv
import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}

CLUSTERS = {
    "jing_jin_ji": {
        "name": "京津冀（70城样本）",
        "cities": ["北京", "天津", "石家庄", "唐山", "秦皇岛"],
        "note": "国家统计局70城中位于京津冀的5个样本城市。",
    },
    "yangtze_river_delta": {
        "name": "长三角（70城样本）",
        "cities": ["上海", "南京", "杭州", "宁波", "合肥", "无锡", "徐州", "扬州", "温州", "金华", "蚌埠", "安庆"],
        "note": "国家统计局70城中位于长三角四省市的12个样本城市。",
    },
    "greater_bay_area": {
        "name": "粤港澳大湾区（70城样本）",
        "cities": ["广州", "深圳", "惠州"],
        "note": "70城只覆盖广州、深圳、惠州，不等同于大湾区9市+香港+澳门。",
    },
    "chengdu_chongqing": {
        "name": "成渝地区（70城样本）",
        "cities": ["重庆", "成都", "泸州", "南充"],
        "note": "70城中的重庆、成都、泸州、南充样本，不等同于双城经济圈完整范围。",
    },
    "middle_yangtze": {
        "name": "长江中游（70城样本）",
        "cities": ["南昌", "武汉", "长沙", "宜昌", "襄阳", "岳阳", "常德", "九江"],
        "note": "70城中的鄂湘赣8个代表城市，不等同于城市群完整范围。",
    },
}

MARKET_NAMES = {"new": "新建商品住宅", "second_hand": "二手住宅"}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def load_city_prices(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _read_csv(path):
        if not raw.get("date") or not raw.get("city") or raw.get("market") not in MARKET_NAMES:
            continue
        try:
            rows.append({
                **raw,
                "date": datetime.strptime(raw["date"], "%Y-%m-%d").date(),
                "mom_pct": float(raw["mom_pct"]),
                "yoy_pct": float(raw["yoy_pct"]),
                "ytd_avg_pct": float(raw["ytd_avg_pct"]) if raw.get("ytd_avg_pct") not in (None, "") else None,
            })
        except (TypeError, ValueError):
            continue
    return sorted(rows, key=lambda r: (r["date"], r["market"], r["city"]))


def _status(median_mom: float | None, median_yoy: float | None, down: int, observed: int) -> str:
    if median_mom is None or median_yoy is None or observed == 0:
        return "unknown"
    down_share = down / observed
    if median_yoy <= -5.0 and down_share >= 2 / 3:
        return "red"
    if median_yoy < 0 or median_mom < 0 or down_share > 0.5:
        return "yellow"
    return "green"


def _summarize_group(group_id: str, group_name: str, scope: str, note: str, expected: int, rows: list[dict[str, Any]], market: str) -> dict[str, Any] | None:
    subset = [r for r in rows if r["market"] == market]
    if not subset:
        return None
    latest_date = max(r["date"] for r in subset)
    latest = [r for r in subset if r["date"] == latest_date]
    moms = [float(r["mom_pct"]) for r in latest]
    yoys = [float(r["yoy_pct"]) for r in latest]
    up = sum(1 for x in moms if x > 0.05)
    down = sum(1 for x in moms if x < -0.05)
    flat = len(moms) - up - down
    med_mom = median(moms) if moms else None
    med_yoy = median(yoys) if yoys else None
    status = _status(med_mom, med_yoy, down, len(latest))
    source_url = next((r.get("source_url", "") for r in latest if r.get("source_url")), "")
    return {
        "cluster": group_id,
        "cluster_name": group_name,
        "scope": scope,
        "scope_note": note,
        "market": market,
        "market_name": MARKET_NAMES[market],
        "latest_date": latest_date,
        "median_mom_pct": med_mom,
        "median_yoy_pct": med_yoy,
        "up_count": up,
        "down_count": down,
        "flat_count": flat,
        "observed_cities": len(latest),
        "expected_cities": expected,
        "coverage": round(len(latest) / expected * 100.0, 1) if expected else 0.0,
        "status": status,
        "status_icon": STATUS_ICON[status],
        "source_url": source_url,
    }


def summarize_housing(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"summaries": [], "latest_second_hand": []}
    latest_date = max(r["date"] for r in rows)
    current = [r for r in rows if r["date"] == latest_date]
    summaries: list[dict[str, Any]] = []

    all_cities = sorted({r["city"] for r in current})
    for market in MARKET_NAMES:
        summary = _summarize_group(
            "nbs_70", "全国70城总体", "official_universe",
            "国家统计局70个大中城市官方统计总体。", len(all_cities), current, market,
        )
        if summary:
            summaries.append(summary)

    latest_second_hand: list[dict[str, Any]] = []
    by_city_market = {(r["city"], r["market"]): r for r in current}
    for cluster_id, cfg in CLUSTERS.items():
        city_set = set(cfg["cities"])
        cluster_rows = [r for r in current if r["city"] in city_set]
        for market in MARKET_NAMES:
            summary = _summarize_group(cluster_id, cfg["name"], "70_city_sample", cfg["note"], len(cfg["cities"]), cluster_rows, market)
            if summary:
                summaries.append(summary)
        for city in cfg["cities"]:
            row = by_city_market.get((city, "second_hand"))
            if not row:
                continue
            latest_second_hand.append({
                "cluster": cluster_id,
                "cluster_name": cfg["name"],
                "city": city,
                "date": row["date"],
                "mom_pct": row["mom_pct"],
                "yoy_pct": row["yoy_pct"],
                "source_url": row.get("source_url", ""),
            })

    return {"summaries": summaries, "latest_second_hand": latest_second_hand}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def render_markdown(housing: dict[str, Any]) -> str:
    if not housing.get("summaries"):
        return ""
    lines = [
        "## 房地产与城市", "",
        "> 价格层使用国家统计局70城官方样本；经济群卡片只是70城中的城市样本，不代表完整城市群。二手房价格比新房价格更接近家庭资产流动性信号。全国房地产开发、销售和二手房网签指标在“核心指标”中单独计分。", "",
        "### 70城价格与经济群样本", "",
        "| 范围 | 市场 | 数据期 | 环比中位数 | 同比中位数 | 上涨/下跌/持平 | 状态 | 覆盖 |",
        "|---|---|---|---:|---:|---:|:---:|---:|",
    ]
    for r in housing["summaries"]:
        lines.append(
            f"| {r['cluster_name']} | {r['market_name']} | {r['latest_date'].isoformat()} | {_pct(r['median_mom_pct'])} | "
            f"{_pct(r['median_yoy_pct'])} | {r['up_count']}/{r['down_count']}/{r['flat_count']} | {r['status_icon']} | {r['coverage']:.0f}% |"
        )
    lines += ["", "### 二手住宅价格（经济群70城样本）", "", "| 经济群 | 城市 | 数据期 | 环比 | 同比 |", "|---|---|---|---:|---:|"]
    for r in housing.get("latest_second_hand", []):
        lines.append(f"| {r['cluster_name']} | {r['city']} | {r['date'].isoformat()} | {_pct(r['mom_pct'])} | {_pct(r['yoy_pct'])} |")
    lines += ["", "> 城市人口流入仍按年度口径建设；不会把月度房价变化伪装成人口流动。下一层应接各城市年度统计公报中的常住人口、净增人口及就业人口。"]
    return "\n".join(lines) + "\n"


def render_html(housing: dict[str, Any]) -> str:
    if not housing.get("summaries"):
        return ""
    cards = []
    for r in housing["summaries"]:
        scope = "官方70城总体" if r["scope"] == "official_universe" else "70城样本"
        cards.append(
            "<div class='card regional-card'>"
            f"<div class='muted'>{html.escape(r['cluster_name'])} · {scope}</div>"
            f"<h3>{html.escape(r['market_name'])}</h3>"
            f"<div class='score'>{_pct(r['median_yoy_pct'])} {r['status_icon']}</div>"
            f"<div>环比中位数 {_pct(r['median_mom_pct'])}</div>"
            f"<div>上涨/下跌/持平 {r['up_count']}/{r['down_count']}/{r['flat_count']}</div>"
            f"<div class='muted'>{r['latest_date'].isoformat()} · 覆盖 {r['coverage']:.0f}%</div>"
            "</div>"
        )
    rows = []
    for r in housing.get("latest_second_hand", []):
        rows.append(
            "<tr>"
            f"<td>{html.escape(r['cluster_name'])}</td><td>{html.escape(r['city'])}</td>"
            f"<td>{r['date'].isoformat()}</td><td>{_pct(r['mom_pct'])}</td><td>{_pct(r['yoy_pct'])}</td>"
            "</tr>"
        )
    return (
        "<section><h2>房地产与城市</h2>"
        "<p class='muted'>价格层使用国家统计局70城官方样本；经济群卡片只是70城中的城市样本，不代表完整城市群。二手房价格更接近家庭资产流动性信号；全国开发、销售和网签指标在核心指标中单独计分。</p>"
        f"<div class='grid'>{''.join(cards)}</div>"
        "<h3>二手住宅价格（经济群70城样本）</h3>"
        "<table><thead><tr><th>经济群</th><th>城市</th><th>数据期</th><th>环比</th><th>同比</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "<p class='muted'>城市人口流入继续按年度统计公报建设；不会用月度房价替代人口流动。</p></section>"
    )


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def enrich_reports(output_dir: str | Path, housing: dict[str, Any]) -> None:
    if not housing.get("summaries"):
        return
    out = Path(output_dir)
    html_path = out / "index.html"
    md_path = out / "report.md"
    html_text = html_path.read_text(encoding="utf-8")
    marker = "<section><h2>核心指标</h2>"
    section = render_html(housing)
    html_text = html_text.replace(marker, section + marker, 1) if marker in html_text else html_text.replace("</main>", section + "</main>", 1)
    html_path.write_text(html_text, encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    md_marker = "\n## 核心指标"
    md_section = "\n" + render_markdown(housing).rstrip() + "\n"
    md_text = md_text.replace(md_marker, md_section + md_marker, 1) if md_marker in md_text else md_text + md_section
    md_path.write_text(md_text, encoding="utf-8")
    _write_csv(out / "housing_summary.csv", housing.get("summaries", []), [
        "cluster", "cluster_name", "scope", "scope_note", "market", "market_name", "latest_date",
        "median_mom_pct", "median_yoy_pct", "up_count", "down_count", "flat_count", "observed_cities",
        "expected_cities", "coverage", "status", "source_url",
    ])
    _write_csv(out / "housing_latest_second_hand.csv", housing.get("latest_second_hand", []), [
        "cluster", "cluster_name", "city", "date", "mom_pct", "yoy_pct", "source_url",
    ])
