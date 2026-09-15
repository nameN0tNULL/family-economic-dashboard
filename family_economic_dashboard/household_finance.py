from __future__ import annotations

import csv
import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PRIVATE_INDICATORS = [
    "cash_runway_months",
    "debt_service_ratio",
    "household_savings_rate",
    "fixed_obligation_ratio",
    "primary_income_loss_runway_months",
]
MACRO_INDICATORS = [
    "national_real_disposable_income_yoy",
    "national_income_consumption_gap_pp",
    "household_long_term_loans",
]


@dataclass(frozen=True)
class HouseholdSnapshot:
    date: Any
    liquid_assets: float
    after_tax_income: float
    essential_expenses: float
    debt_payments: float
    total_expenses: float
    stable_income_if_primary_lost: float
    note: str = ""


def load_private_snapshots(path: str | Path) -> list[HouseholdSnapshot]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Private household finance file not found: {p}")
    rows: list[HouseholdSnapshot] = []
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "date", "liquid_assets", "after_tax_income", "essential_expenses",
            "debt_payments", "total_expenses", "stable_income_if_primary_lost",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"private household finance missing columns: {sorted(missing)}")
        for raw in reader:
            if not raw.get("date"):
                continue
            values = {k: float(raw[k]) for k in required - {"date"}}
            if any(v < 0 for v in values.values()):
                raise ValueError(f"negative household finance value on {raw['date']}")
            if values["after_tax_income"] <= 0:
                raise ValueError(f"after_tax_income must be > 0 on {raw['date']}")
            mandatory = values["essential_expenses"] + values["debt_payments"]
            if mandatory <= 0:
                raise ValueError(f"essential_expenses + debt_payments must be > 0 on {raw['date']}")
            if values["total_expenses"] + 1e-9 < mandatory:
                raise ValueError(f"total_expenses cannot be below essential_expenses + debt_payments on {raw['date']}")
            rows.append(HouseholdSnapshot(
                date=datetime.strptime(raw["date"], "%Y-%m-%d").date(),
                liquid_assets=values["liquid_assets"],
                after_tax_income=values["after_tax_income"],
                essential_expenses=values["essential_expenses"],
                debt_payments=values["debt_payments"],
                total_expenses=values["total_expenses"],
                stable_income_if_primary_lost=values["stable_income_if_primary_lost"],
                note=raw.get("note", ""),
            ))
    return sorted(rows, key=lambda r: r.date)


def snapshots_to_observations(rows: list[HouseholdSnapshot]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for row in rows:
        mandatory = row.essential_expenses + row.debt_payments
        cash_runway = row.liquid_assets / mandatory
        debt_service = row.debt_payments / row.after_tax_income * 100.0
        savings_rate = (row.after_tax_income - row.total_expenses) / row.after_tax_income * 100.0
        fixed_obligation = mandatory / row.after_tax_income * 100.0
        shock_burn = mandatory - row.stable_income_if_primary_lost
        # If remaining stable income fully covers mandatory outflows, there is no monthly cash draw.
        # Cap the display metric at 120 months; the risk thresholds are far below that cap.
        primary_loss_runway = 120.0 if shock_burn <= 0 else row.liquid_assets / shock_burn
        note = "私密家庭汇总推导；不含账户/交易明细；原始金额不写入报告"
        if row.note:
            note += f"；{row.note}"
        values = {
            "cash_runway_months": cash_runway,
            "debt_service_ratio": debt_service,
            "household_savings_rate": savings_rate,
            "fixed_obligation_ratio": fixed_obligation,
            "primary_income_loss_runway_months": primary_loss_runway,
        }
        for indicator, value in values.items():
            observations.append({
                "date": row.date,
                "indicator": indicator,
                "value": value,
                "note": note,
                "source_url": "",
            })
    return observations


def _fmt(value: float | None, unit: str) -> str:
    if value is None:
        return "—"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "月":
        return "≥120月" if value >= 119.95 else f"{value:.1f}月"
    if unit == "pp":
        return f"{value:+.1f}pp"
    if unit == "亿元":
        return f"{value:,.0f}亿元"
    return f"{value:.1f}{unit}"


def _find(result: Any, indicator_id: str) -> dict[str, Any] | None:
    return next((r for r in result.indicators if r["indicator"] == indicator_id), None)


def render_markdown(result: Any, private_loaded: bool) -> str:
    dim = next((d for d in result.dimensions if d["dimension"] == "household"), None)
    score = "—" if not dim or dim["score"] is None else f"{dim['score']:.1f}"
    coverage = 0.0 if not dim else float(dim["coverage"])
    lines = [
        "## 家庭财务安全", "",
        f"> 家庭财务安全评分 {score}，覆盖率 {coverage:.1f}%。私人家庭数据默认不进入公开仓库或 GitHub Pages；全国指标只是背景，不替代家庭自身现金流。", "",
        "### 私人安全垫", "",
    ]
    if not private_loaded:
        lines += [
            "当前公开构建未加载私人家庭财务文件。这是安全默认值。", "",
            "本地私密构建会计算：零收入现金跑道、月供/税后收入、储蓄率、固定必要支出率、主收入中断后的现金跑道。", "",
        ]
    else:
        lines += ["| 指标 | 当前值 | 状态 |", "|---|---:|:---:|"]
        for indicator_id in PRIVATE_INDICATORS:
            r = _find(result, indicator_id)
            if not r:
                continue
            lines.append(f"| {r['name']} | {_fmt(r['current'], r['unit'])} | {r['status_icon']} |")
        lines.append("")
    lines += ["### 全国家庭金融背景", "", "| 指标 | 当前值 | 状态 | 数据期 |", "|---|---:|:---:|---|"]
    for indicator_id in MACRO_INDICATORS:
        r = _find(result, indicator_id)
        if not r or r["current"] is None:
            continue
        current_date = r["current_date"].isoformat() if r["current_date"] else "—"
        lines.append(f"| {r['name']} | {_fmt(r['current'], r['unit'])} | {r['status_icon']} | {current_date} |")
    lines += [
        "",
        "> 解释顺序：先看家庭私人安全垫，再看全国居民收入/消费和住户信用环境。全国数据改善不能抵消家庭高杠杆或现金跑道不足。",
    ]
    return "\n".join(lines) + "\n"


def render_html(result: Any, private_loaded: bool) -> str:
    dim = next((d for d in result.dimensions if d["dimension"] == "household"), None)
    score = "—" if not dim or dim["score"] is None else f"{dim['score']:.1f}"
    coverage = 0.0 if not dim else float(dim["coverage"])
    private_cards: list[str] = []
    if private_loaded:
        for indicator_id in PRIVATE_INDICATORS:
            r = _find(result, indicator_id)
            if not r:
                continue
            private_cards.append(
                "<div class='card regional-card'>"
                f"<div class='muted'>私人安全垫</div><h3>{html.escape(r['name'])}</h3>"
                f"<div class='score'>{html.escape(_fmt(r['current'], r['unit']))} {r['status_icon']}</div>"
                f"<div class='muted'>{r['current_date'].isoformat() if r['current_date'] else '—'}</div></div>"
            )
        private_html = f"<div class='grid'>{''.join(private_cards)}</div>"
    else:
        private_html = (
            "<p class='muted'>公开构建未加载私人家庭财务文件（安全默认）。本地私密构建可计算："
            "零收入现金跑道、偿债率、储蓄率、固定必要支出率、主收入中断现金跑道。</p>"
        )
    macro_cards: list[str] = []
    for indicator_id in MACRO_INDICATORS:
        r = _find(result, indicator_id)
        if not r or r["current"] is None:
            continue
        macro_cards.append(
            "<div class='card regional-card'>"
            f"<div class='muted'>全国背景 · {r['current_date'].isoformat() if r['current_date'] else '—'}</div>"
            f"<h3>{html.escape(r['name'])}</h3>"
            f"<div class='score'>{html.escape(_fmt(r['current'], r['unit']))} {r['status_icon']}</div>"
            "</div>"
        )
    return (
        "<section><h2>家庭财务安全</h2>"
        f"<p class='muted'>评分 {score} · 覆盖率 {coverage:.1f}% 。私人家庭数据不进入公开仓库/Pages；全国指标只作背景。</p>"
        "<h3>私人安全垫</h3>" + private_html +
        "<h3>全国家庭金融背景</h3>" + (f"<div class='grid'>{''.join(macro_cards)}</div>" if macro_cards else "<p class='muted'>暂无可用全国背景数据。</p>") +
        "<p class='muted'>判断顺序：先看家庭自身现金流与杠杆，再看全国居民收入、消费和住户信用环境。</p></section>"
    )


def enrich_reports(output_dir: str | Path, result: Any, private_loaded: bool) -> None:
    out = Path(output_dir)
    html_path = out / "index.html"
    md_path = out / "report.md"
    marker = "<section><h2>核心指标</h2>"
    html_text = html_path.read_text(encoding="utf-8")
    section = render_html(result, private_loaded)
    html_text = html_text.replace(marker, section + marker, 1) if marker in html_text else html_text.replace("</main>", section + "</main>", 1)
    html_path.write_text(html_text, encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    md_marker = "\n## 核心指标"
    md_section = "\n" + render_markdown(result, private_loaded).rstrip() + "\n"
    md_text = md_text.replace(md_marker, md_section + md_marker, 1) if md_marker in md_text else md_text + md_section
    md_path.write_text(md_text, encoding="utf-8")
