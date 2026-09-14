from __future__ import annotations

import csv
import html
from pathlib import Path

from .engine import DashboardResult, STATUS_ICON


def _fmt(value: float | None, digits: int = 1) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _change(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def render_markdown(result: DashboardResult) -> str:
    lines = [
        f"# 家庭经济周期盘点（截至 {result.as_of.isoformat()}）", "",
        f"**综合评分：{result.overall_score:.1f} / 100 {STATUS_ICON[result.overall_status]}**", "",
        "## 五大维度", "", "| 维度 | 分数 | 状态 | 红灯 | 黄灯 |", "|---|---:|:---:|---:|---:|",
    ]
    for r in result.dimensions:
        lines.append(f"| {r['name']} | {r['score']:.1f} | {r['status_icon']} | {r['red_count']} | {r['yellow_count']} |")
    lines += ["", "## 核心指标", "", "| 指标 | 本期 | 环比 | 半年 | 同比 | 状态 |", "|---|---:|---:|---:|---:|:---:|"]
    for r in result.indicators:
        current = "—" if r["current"] is None else f"{r['current']:.1f}{r['unit']}"
        lines.append(f"| {r['name']} | {current} | {_change(r['mom_pct'])} | {_change(r['six_month_pct'])} | {_change(r['yoy_pct'])} | {r['status_icon']} |")
    lines += ["", "## 共振信号", ""]
    if result.resonance:
        for item in result.resonance:
            level = "风险明显" if item["level"] == "risk" else "需要关注"
            lines.append(f"- **{item['name']}**：{item['red_count']} 个红灯，{level}。")
    else:
        lines.append("- 当前没有达到同一维度 2 个红灯以上的共振条件。")
    lines += ["", "## 固定复盘问题", "", "1. 我的工作风险是在上升还是下降？", "2. 如果收入突然中断，家庭能撑多久？", "3. 我的房产和所在城市是在改善还是恶化？", "4. 有没有出现需要真正改变家庭决策的持续性信号？", "", "> 本报告用于趋势盘点，不构成投资、就业或房地产交易建议。"]
    return "\n".join(lines) + "\n"


def render_html(result: DashboardResult) -> str:
    cards = "".join(f"<div class='card'><h3>{html.escape(r['name'])}</h3><div class='score'>{r['score']:.1f}</div><div>{r['status_icon']} 红 {r['red_count']} / 黄 {r['yellow_count']}</div></div>" for r in result.dimensions)
    rows = "".join("<tr>" + f"<td>{html.escape(r['name'])}</td><td>{_fmt(r['current'])}{html.escape(r['unit'])}</td><td>{_change(r['mom_pct'])}</td><td>{_change(r['six_month_pct'])}</td><td>{_change(r['yoy_pct'])}</td><td>{r['status_icon']}</td>" + "</tr>" for r in result.indicators)
    resonance = "".join(f"<li><strong>{html.escape(x['name'])}</strong>：{x['red_count']} 个红灯，{'风险明显' if x['level']=='risk' else '需要关注'}</li>" for x in result.resonance) or "<li>当前没有达到同一维度 2 个红灯以上的共振条件。</li>"
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>家庭经济周期盘点</title><style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f6f7f9;color:#1f2328}}main{{max-width:1100px;margin:auto;padding:32px 20px}}.hero{{background:white;border-radius:14px;padding:24px;margin-bottom:20px}}.big{{font-size:42px;font-weight:700}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0}}.card{{background:white;border-radius:12px;padding:18px}}.score{{font-size:28px;font-weight:700;margin:8px 0}}table{{width:100%;border-collapse:collapse;background:white;border-radius:12px;overflow:hidden}}th,td{{padding:11px 12px;border-bottom:1px solid #eaeef2;text-align:right}}th:first-child,td:first-child{{text-align:left}}section{{margin:24px 0}}.muted{{color:#636c76}}@media(max-width:700px){{table{{font-size:13px}}th,td{{padding:8px 6px}}}}
</style></head><body><main><div class="hero"><div class="muted">截至 {result.as_of.isoformat()}</div><h1>家庭经济周期盘点</h1><div class="big">{result.overall_score:.1f} {STATUS_ICON[result.overall_status]}</div><div class="muted">综合评分 / 100</div></div><section><h2>五大维度</h2><div class="grid">{cards}</div></section><section><h2>核心指标</h2><table><thead><tr><th>指标</th><th>本期</th><th>环比</th><th>半年</th><th>同比</th><th>状态</th></tr></thead><tbody>{rows}</tbody></table></section><section><h2>共振信号</h2><ul>{resonance}</ul></section><section><h2>固定复盘问题</h2><ol><li>我的工作风险是在上升还是下降？</li><li>如果收入突然中断，家庭能撑多久？</li><li>我的房产和所在城市是在改善还是恶化？</li><li>有没有出现需要真正改变家庭决策的持续性信号？</li></ol></section><p class="muted">本报告用于趋势盘点，不构成投资、就业或房地产交易建议。</p></main></body></html>'''


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def write_reports(result: DashboardResult, output_dir: str | Path) -> None:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(render_markdown(result), encoding="utf-8")
    (out / "index.html").write_text(render_html(result), encoding="utf-8")
    _write_csv(out / "indicator_summary.csv", result.indicators, ["indicator","name","dimension","frequency","unit","current","current_date","mom_pct","six_month_pct","yoy_pct","status","score","source"])
    _write_csv(out / "dimension_summary.csv", result.dimensions, ["dimension","name","weight","score","status","red_count","yellow_count"])
