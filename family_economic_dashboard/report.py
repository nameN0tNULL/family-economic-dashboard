from __future__ import annotations

import csv
import html
from pathlib import Path

from .engine import DashboardResult, STATUS_ICON


def _fmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _score(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}"


def _change(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def _pp(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}pp"


def _regional_markdown(regional: dict | None) -> list[str]:
    if not regional or not regional.get("summaries"):
        return []
    lines = [
        "",
        "## 区域经济群",
        "",
        "> 区域层用于判断宏观分化，不直接计入家庭综合评分。大湾区当前使用广东全省作为月度代理，明确不等同于9市+香港+澳门精确口径。",
        "",
        "| 经济群 | 口径 | 指标 | 数据期 | 中位/代理增速 | 正/负 | 改善/恶化 | 状态 | 覆盖 |",
        "|---|---|---|---|---:|---:|---:|:---:|---:|",
    ]
    for r in regional["summaries"]:
        scope = "精确成员" if r["scope"] == "exact" else "代理"
        lines.append(
            f"| {r['cluster_name']} | {scope} | {r['indicator_name']} | {r['latest_date'].isoformat()} | "
            f"{_change(r['median_growth'])} | {r['positive_count']}/{r['negative_count']} | "
            f"{r['improving_count']}/{r['deteriorating_count']} | {r['status_icon']} | {r['coverage']:.0f}% |"
        )
    lines += [
        "",
        "### 成员最新变化",
        "",
        "| 经济群 | 地区 | 指标 | 本期 | 上期 | 变化 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for r in regional["latest_rows"]:
        lines.append(
            f"| {r['cluster_name']} | {r['region']} | {r['indicator_name']} | {_change(r['value'])} | "
            f"{_change(r['previous_value'])} | {_pp(r['delta_pp'])} |"
        )
    return lines


def render_markdown(result: DashboardResult, regional: dict | None = None) -> str:
    overall = "—" if result.overall_score is None else f"{result.overall_score:.1f} / 100"
    lines = [
        f"# 家庭经济周期盘点（截至 {result.as_of.isoformat()}）", "",
        f"**综合评分：{overall} {STATUS_ICON[result.overall_status]}**  ·  **数据覆盖率：{result.overall_coverage:.1f}%**", "",
        "> 缺失数据不计入评分；覆盖率低时综合分只能代表已采集部分。", "",
        "## 五大维度", "", "| 维度 | 分数 | 状态 | 覆盖率 | 红灯 | 黄灯 |", "|---|---:|:---:|---:|---:|---:|",
    ]
    for r in result.dimensions:
        lines.append(f"| {r['name']} | {_score(r['score'])} | {r['status_icon']} | {r['coverage']:.1f}% | {r['red_count']} | {r['yellow_count']} |")
    lines += _regional_markdown(regional)
    lines += ["", "## 核心指标", "", "| 指标 | 本期 | 数据期 | 环比 | 半年 | 同比 | 状态 | 来源 |", "|---|---:|---|---:|---:|---:|:---:|---|"]
    for r in result.indicators:
        current = "—" if r["current"] is None else f"{r['current']:.1f}{r['unit']}"
        d = r["current_date"].isoformat() if r["current_date"] else "—"
        src = f"[官方原文]({r['source_url']})" if r["source_url"] else r["source"]
        lines.append(f"| {r['name']} | {current} | {d} | {_change(r['mom_pct'])} | {_change(r['six_month_pct'])} | {_change(r['yoy_pct'])} | {r['status_icon']} | {src} |")
    lines += ["", "## 共振信号", ""]
    if result.resonance:
        for item in result.resonance:
            level = "风险明显" if item["level"] == "risk" else "需要关注"
            lines.append(f"- **{item['name']}**：{item['red_count']} 个红灯，{level}。")
    else:
        lines.append("- 当前没有达到同一维度 2 个红灯以上的共振条件。")
    lines += ["", "## 固定复盘问题", "", "1. 我的工作风险是在上升还是下降？", "2. 如果收入突然中断，家庭能撑多久？", "3. 我的房产和所在城市是在改善还是恶化？", "4. 有没有出现需要真正改变家庭决策的持续性信号？", "", "> 本报告用于趋势盘点，不构成投资、就业或房地产交易建议。"]
    return "\n".join(lines) + "\n"


def _regional_html(regional: dict | None) -> str:
    if not regional or not regional.get("summaries"):
        return ""
    cards = []
    for r in regional["summaries"]:
        scope = "精确成员" if r["scope"] == "exact" else "广东代理"
        cards.append(
            "<div class='card regional-card'>"
            f"<div class='muted'>{html.escape(r['cluster_name'])} · {scope}</div>"
            f"<h3>{html.escape(r['indicator_name'])}</h3>"
            f"<div class='score'>{_change(r['median_growth'])} {r['status_icon']}</div>"
            f"<div>正/负 {r['positive_count']}/{r['negative_count']} · 改善/恶化 {r['improving_count']}/{r['deteriorating_count']}</div>"
            f"<div class='muted'>{r['latest_date'].isoformat()} · 覆盖 {r['coverage']:.0f}%</div>"
            "</div>"
        )
    row_parts = []
    for r in regional["latest_rows"]:
        row_parts.append(
            "<tr>"
            f"<td>{html.escape(r['cluster_name'])}</td>"
            f"<td>{html.escape(r['region'])}</td>"
            f"<td>{html.escape(r['indicator_name'])}</td>"
            f"<td>{_change(r['value'])}</td>"
            f"<td>{_change(r['previous_value'])}</td>"
            f"<td>{_pp(r['delta_pp'])}</td>"
            "</tr>"
        )
    return (
        "<section><h2>区域经济群</h2>"
        "<p class='muted'>区域层用于判断宏观分化，不直接计入家庭综合评分。粤港澳大湾区当前以广东全省作为月度代理，不能解释为9市+香港+澳门精确总量。</p>"
        f"<div class='grid'>{''.join(cards)}</div>"
        "<h3>成员最新变化</h3>"
        "<table><thead><tr><th>经济群</th><th>地区</th><th>指标</th><th>本期</th><th>上期</th><th>变化</th></tr></thead>"
        f"<tbody>{''.join(row_parts)}</tbody></table></section>"
    )


def render_html(result: DashboardResult, regional: dict | None = None) -> str:
    cards = "".join(f"<div class='card'><h3>{html.escape(r['name'])}</h3><div class='score'>{_score(r['score'])}</div><div>{r['status_icon']} 覆盖 {r['coverage']:.0f}% · 红 {r['red_count']} / 黄 {r['yellow_count']}</div></div>" for r in result.dimensions)
    row_parts = []
    for r in result.indicators:
        source = html.escape(r["source"])
        if r["source_url"]:
            source = f"<a href='{html.escape(r['source_url'], quote=True)}' target='_blank' rel='noreferrer'>官方原文</a>"
        row_parts.append("<tr>" + f"<td>{html.escape(r['name'])}</td><td>{_fmt(r['current'])}{html.escape(r['unit'])}</td><td>{r['current_date'].isoformat() if r['current_date'] else '—'}</td><td>{_change(r['mom_pct'])}</td><td>{_change(r['six_month_pct'])}</td><td>{_change(r['yoy_pct'])}</td><td>{r['status_icon']}</td><td>{source}</td>" + "</tr>")
    rows = "".join(row_parts)
    resonance = "".join(f"<li><strong>{html.escape(x['name'])}</strong>：{x['red_count']} 个红灯，{'风险明显' if x['level']=='risk' else '需要关注'}</li>" for x in result.resonance) or "<li>当前没有达到同一维度 2 个红灯以上的共振条件。</li>"
    overall = "—" if result.overall_score is None else f"{result.overall_score:.1f}"
    regional_html = _regional_html(regional)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>家庭经济周期盘点</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f6f7f9;color:#1f2328}}main{{max-width:1180px;margin:auto;padding:32px 20px}}.hero{{background:white;border-radius:14px;padding:24px;margin-bottom:20px}}.big{{font-size:42px;font-weight:700}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0}}.card{{background:white;border-radius:12px;padding:18px}}.regional-card{{min-height:140px}}.score{{font-size:28px;font-weight:700;margin:8px 0}}table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:11px 12px;border-bottom:1px solid #eaeef2;text-align:right}}th:first-child,td:first-child{{text-align:left}}section{{margin:24px 0}}.muted{{color:#636c76}}a{{color:inherit}}@media(max-width:700px){{table{{font-size:12px}}th,td{{padding:7px 5px}}}}
</style></head><body><main><div class="hero"><div class="muted">截至 {result.as_of.isoformat()}</div><h1>家庭经济周期盘点</h1><div class="big">{overall} {STATUS_ICON[result.overall_status]}</div><div class="muted">综合评分 / 100 · 数据覆盖率 {result.overall_coverage:.1f}% · 缺失项不计入评分</div></div><section><h2>五大维度</h2><div class="grid">{cards}</div></section>{regional_html}<section><h2>核心指标</h2><table><thead><tr><th>指标</th><th>本期</th><th>数据期</th><th>环比</th><th>半年</th><th>同比</th><th>状态</th><th>来源</th></tr></thead><tbody>{rows}</tbody></table></section><section><h2>共振信号</h2><ul>{resonance}</ul></section><section><h2>固定复盘问题</h2><ol><li>我的工作风险是在上升还是下降？</li><li>如果收入突然中断，家庭能撑多久？</li><li>我的房产和所在城市是在改善还是恶化？</li><li>有没有出现需要真正改变家庭决策的持续性信号？</li></ol></section><p class="muted">本报告用于趋势盘点，不构成投资、就业或房地产交易建议。</p></main></body></html>'''


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def write_reports(result: DashboardResult, output_dir: str | Path, regional: dict | None = None) -> None:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(render_markdown(result, regional), encoding="utf-8")
    (out / "index.html").write_text(render_html(result, regional), encoding="utf-8")
    _write_csv(out / "indicator_summary.csv", result.indicators, ["indicator","name","dimension","frequency","unit","current","current_date","mom_pct","six_month_pct","yoy_pct","status","score","source","source_url","note","collection"])
    _write_csv(out / "dimension_summary.csv", result.dimensions, ["dimension","name","weight","score","status","coverage","known_count","total_count","red_count","yellow_count"])
    if regional:
        _write_csv(out / "regional_summary.csv", regional.get("summaries", []), ["cluster","cluster_name","scope","indicator","indicator_name","latest_date","previous_date","median_growth","min_growth","max_growth","positive_count","negative_count","zero_count","improving_count","deteriorating_count","unchanged_count","comparable_count","observed_regions","expected_regions","coverage","status"])
        _write_csv(out / "regional_latest.csv", regional.get("latest_rows", []), ["cluster","cluster_name","scope","indicator","indicator_name","region","region_code","date","value","previous_date","previous_value","delta_pp","source","source_url"])
