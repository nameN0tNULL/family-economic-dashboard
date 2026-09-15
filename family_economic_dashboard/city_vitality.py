from __future__ import annotations

import csv
import html
from pathlib import Path
from statistics import median
from typing import Any

STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}
CLUSTER_NAMES = {
    "jing_jin_ji": "京津冀核心城市",
    "yangtze_river_delta": "长三角核心城市",
    "greater_bay_area": "粤港澳大湾区内地核心城市",
    "chengdu_chongqing": "成渝核心城市",
    "middle_yangtze": "长江中游核心城市",
}


def load_city_population(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            try:
                population = float(raw["resident_population_wan"])
                change = float(raw["change_wan"])
                previous = population - change
                change_pct = change / previous * 100.0 if previous else None
                rows.append({
                    **raw,
                    "year": int(raw["year"]),
                    "resident_population_wan": population,
                    "change_wan": change,
                    "change_pct": change_pct,
                })
            except (KeyError, TypeError, ValueError):
                continue
    return sorted(rows, key=lambda r: (r["year"], r["cluster"], r["city"]))


def summarize_city_population(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"latest_year": None, "cluster_summaries": [], "cities": []}
    latest_year = max(r["year"] for r in rows)
    current = [r for r in rows if r["year"] == latest_year]
    summaries = []
    for cluster in CLUSTER_NAMES:
        subset = [r for r in current if r["cluster"] == cluster]
        if not subset:
            continue
        positive = sum(1 for r in subset if r["change_wan"] > 0)
        negative = sum(1 for r in subset if r["change_wan"] < 0)
        flat = len(subset) - positive - negative
        changes = [float(r["change_pct"]) for r in subset if r["change_pct"] is not None]
        med = median(changes) if changes else None
        if negative / len(subset) >= 2 / 3:
            status = "red"
        elif negative > 0 or (med is not None and med <= 0):
            status = "yellow"
        else:
            status = "green"
        summaries.append({
            "cluster": cluster,
            "cluster_name": CLUSTER_NAMES[cluster],
            "year": latest_year,
            "sample_cities": len(subset),
            "positive_count": positive,
            "negative_count": negative,
            "flat_count": flat,
            "median_change_pct": med,
            "status": status,
            "status_icon": STATUS_ICON[status],
        })
    return {"latest_year": latest_year, "cluster_summaries": summaries, "cities": current}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.2f}%"


def render_html(city: dict[str, Any]) -> str:
    if not city.get("cities"):
        return ""
    cards = []
    for r in city["cluster_summaries"]:
        cards.append(
            "<div class='card regional-card'>"
            f"<div class='muted'>{html.escape(r['cluster_name'])} · 年度样本</div>"
            f"<h3>常住人口变化</h3><div class='score'>{_pct(r['median_change_pct'])} {r['status_icon']}</div>"
            f"<div>增加/减少/持平 {r['positive_count']}/{r['negative_count']}/{r['flat_count']}</div>"
            f"<div class='muted'>{r['year']}年 · {r['sample_cities']}个核心城市</div></div>"
        )
    rows = []
    for r in city["cities"]:
        source = html.escape(r.get("source_url", ""), quote=True)
        city_name = html.escape(r["city"])
        city_cell = f"<a href='{source}' target='_blank' rel='noreferrer'>{city_name}</a>" if source else city_name
        rows.append(
            "<tr>"
            f"<td>{html.escape(CLUSTER_NAMES.get(r['cluster'], r['cluster']))}</td><td>{city_cell}</td>"
            f"<td>{r['resident_population_wan']:.2f}万</td><td>{r['change_wan']:+.2f}万</td><td>{_pct(r['change_pct'])}</td>"
            "</tr>"
        )
    return (
        "<section><h2>城市人口与活力</h2>"
        "<p class='muted'>年度常住人口来自各城市官方统计公报。这里是核心城市样本，不是城市群总人口；人口增减只作为城市吸引力和住房长期需求的慢变量，不与月度房价混为一谈。</p>"
        f"<div class='grid'>{''.join(cards)}</div>"
        "<table><thead><tr><th>区域</th><th>城市</th><th>常住人口</th><th>年度增减</th><th>增减幅</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></section>"
    )


def render_markdown(city: dict[str, Any]) -> str:
    if not city.get("cities"):
        return ""
    lines = [
        "## 城市人口与活力", "",
        "> 年度常住人口来自各城市官方统计公报。这里是核心城市样本，不是城市群总人口；人口增减作为住房长期需求的慢变量。", "",
        "| 区域 | 城市 | 常住人口 | 年度增减 | 增减幅 | 来源 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in city["cities"]:
        source = f"[官方公报]({r['source_url']})" if r.get("source_url") else r.get("source", "")
        lines.append(
            f"| {CLUSTER_NAMES.get(r['cluster'], r['cluster'])} | {r['city']} | {r['resident_population_wan']:.2f}万 | "
            f"{r['change_wan']:+.2f}万 | {_pct(r['change_pct'])} | {source} |"
        )
    return "\n".join(lines) + "\n"


def enrich_reports(output_dir: str | Path, city: dict[str, Any]) -> None:
    if not city.get("cities"):
        return
    out = Path(output_dir)
    html_path = out / "index.html"
    html_text = html_path.read_text(encoding="utf-8")
    marker = "<section><h2>核心指标</h2>"
    section = render_html(city)
    html_text = html_text.replace(marker, section + marker, 1) if marker in html_text else html_text.replace("</main>", section + "</main>", 1)
    html_path.write_text(html_text, encoding="utf-8")

    md_path = out / "report.md"
    md_text = md_path.read_text(encoding="utf-8")
    md_marker = "\n## 核心指标"
    md_section = "\n" + render_markdown(city).rstrip() + "\n"
    md_text = md_text.replace(md_marker, md_section + md_marker, 1) if md_marker in md_text else md_text + md_section
    md_path.write_text(md_text, encoding="utf-8")

    with (out / "city_vitality.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["year", "cluster", "city", "resident_population_wan", "change_wan", "change_pct", "source", "source_url", "previous_source_url", "note"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(city["cities"])
