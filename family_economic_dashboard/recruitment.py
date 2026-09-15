from __future__ import annotations

import csv
import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def load_market(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _read_csv(path):
        if not raw.get("period_end") or not raw.get("scope") or not raw.get("job") or not raw.get("salary_wan_month"):
            continue
        rows.append({
            **raw,
            "period_end": datetime.strptime(raw["period_end"], "%Y-%m-%d").date(),
            "salary_wan_month": float(raw["salary_wan_month"]),
        })
    return sorted(rows, key=lambda r: (r["scope"], r["period_end"], r["job"]))


def load_search_snapshots(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _read_csv(path):
        if not raw.get("date") or not raw.get("platform") or not raw.get("city") or not raw.get("keyword"):
            continue
        row: dict[str, Any] = {**raw, "date": datetime.strptime(raw["date"], "%Y-%m-%d").date(), "result_count": None, "salary_median_k": None}
        for field in ("result_count", "salary_median_k"):
            if raw.get(field) not in (None, ""):
                row[field] = float(raw[field])
        rows.append(row)
    return sorted(rows, key=lambda r: (r["date"], r["platform"], r["city"], r["keyword"]))


def search_snapshots_to_observations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_date[row["date"]].append(row)
    observations: list[dict[str, Any]] = []
    for day, items in sorted(by_date.items()):
        counts = [float(x["result_count"]) for x in items if x.get("result_count") is not None]
        salaries = [float(x["salary_median_k"]) for x in items if x.get("salary_median_k") is not None]
        platforms = sorted({x["platform"] for x in items})
        note = f"固定招聘搜索篮子；{len(items)} 条快照；平台：{'/'.join(platforms)}"
        source_url = next((x.get("source_url", "") for x in items if x.get("source_url")), "")
        if counts:
            observations.append({"date": day, "indicator": "job_postings", "value": median(counts), "note": note, "source_url": source_url})
        if salaries:
            observations.append({"date": day, "indicator": "salary_mid", "value": median(salaries), "note": note, "source_url": source_url})
    return observations


def _status(median_qoq: float | None, down: int, comparable: int) -> str:
    if median_qoq is None or comparable == 0:
        return "unknown"
    down_share = down / comparable
    if median_qoq <= -5 and down_share >= 2 / 3:
        return "red"
    if median_qoq <= -3 or down_share > 0.5:
        return "yellow"
    return "green"


def summarize_recruitment(market_rows: list[dict[str, Any]], search_rows: list[dict[str, Any]]) -> dict[str, Any]:
    market_summaries: list[dict[str, Any]] = []
    latest_jobs: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in market_rows:
        grouped[row["scope"]].append(row)

    for scope, rows in sorted(grouped.items()):
        periods = sorted({r["period_end"] for r in rows})
        if not periods:
            continue
        latest_period = periods[-1]
        previous_period = periods[-2] if len(periods) > 1 else None
        latest = [r for r in rows if r["period_end"] == latest_period]
        previous = [r for r in rows if r["period_end"] == previous_period] if previous_period else []
        latest_map = {r["job"]: r for r in latest}
        prev_map = {r["job"]: r for r in previous}
        common = sorted(set(latest_map) & set(prev_map))
        changes: list[float] = []
        up = down = flat = 0
        for job in common:
            old = float(prev_map[job]["salary_wan_month"])
            new = float(latest_map[job]["salary_wan_month"])
            if not old:
                continue
            pct = (new / old - 1.0) * 100.0
            changes.append(pct)
            if pct > 0.05:
                up += 1
            elif pct < -0.05:
                down += 1
            else:
                flat += 1
        med_qoq = median(changes) if changes else None
        status = _status(med_qoq, down, len(changes))
        source_url = next((r.get("source_url", "") for r in latest if r.get("source_url")), "")
        market_summaries.append({
            "scope": scope,
            "latest_period": latest_period,
            "previous_period": previous_period,
            "hot_job_count": len(latest),
            "median_salary_k": median([float(r["salary_wan_month"]) for r in latest]) * 10.0 if latest else None,
            "median_qoq_pct": med_qoq,
            "up_count": up,
            "down_count": down,
            "flat_count": flat,
            "comparable_count": len(changes),
            "entrants": sorted(set(latest_map) - set(prev_map)),
            "exits": sorted(set(prev_map) - set(latest_map)),
            "status": status,
            "status_icon": STATUS_ICON[status],
            "source_url": source_url,
        })
        for row in sorted(latest, key=lambda r: float(r["salary_wan_month"]), reverse=True):
            prev = prev_map.get(row["job"])
            old = float(prev["salary_wan_month"]) if prev else None
            new = float(row["salary_wan_month"])
            qoq = (new / old - 1.0) * 100.0 if old else None
            latest_jobs.append({
                "scope": scope,
                "period_end": latest_period,
                "job": row["job"],
                "salary_k": new * 10.0,
                "previous_salary_k": old * 10.0 if old is not None else None,
                "qoq_pct": qoq,
                "source_url": row.get("source_url", ""),
            })

    search_summaries: list[dict[str, Any]] = []
    search_grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in search_rows:
        search_grouped[(row["platform"], row["city"], row["keyword"])].append(row)
    for key, rows in sorted(search_grouped.items()):
        rows = sorted(rows, key=lambda r: r["date"])
        current = rows[-1]
        previous = rows[-2] if len(rows) > 1 else None
        count = current.get("result_count")
        prev_count = previous.get("result_count") if previous else None
        count_change = ((float(count) / float(prev_count) - 1.0) * 100.0 if count is not None and prev_count not in (None, 0) else None)
        salary = current.get("salary_median_k")
        prev_salary = previous.get("salary_median_k") if previous else None
        salary_change = ((float(salary) / float(prev_salary) - 1.0) * 100.0 if salary is not None and prev_salary not in (None, 0) else None)
        search_summaries.append({
            "platform": key[0], "city": key[1], "keyword": key[2], "date": current["date"],
            "result_count": count, "count_change_pct": count_change,
            "salary_median_k": salary, "salary_change_pct": salary_change,
            "source_url": current.get("source_url", ""), "note": current.get("note", ""),
        })

    return {"market_summaries": market_summaries, "latest_jobs": latest_jobs, "search_summaries": search_summaries}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def _num(value: float | None, suffix: str = "") -> str:
    return "—" if value is None else f"{value:.1f}{suffix}"


def render_markdown(recruitment: dict[str, Any]) -> str:
    lines = [
        "## 招聘市场", "",
        "> 官方市场招聘薪酬基准用于判断外部就业市场，不直接计入家庭综合评分；个人固定搜索篮子有数据后，会自动生成“同岗招聘数量”和“同岗薪资中位数”两个就业指标。", "",
        "### 官方招聘市场基准", "",
        "| 区域 | 数据期 | 热门岗位数 | 热门岗位薪酬中位数 | 同岗薪酬环比中位数 | 上涨/下跌/持平 | 状态 |",
        "|---|---|---:|---:|---:|---:|:---:|",
    ]
    for r in recruitment.get("market_summaries", []):
        lines.append(f"| {r['scope']} | {r['latest_period'].isoformat()} | {r['hot_job_count']} | {_num(r['median_salary_k'], 'K/月')} | {_pct(r['median_qoq_pct'])} | {r['up_count']}/{r['down_count']}/{r['flat_count']} | {r['status_icon']} |")
    lines += ["", "### 热门岗位薪酬（最新季度）", "", "| 区域 | 岗位 | 本期 | 上期 | 环比 |", "|---|---|---:|---:|---:|"]
    for r in recruitment.get("latest_jobs", []):
        lines.append(f"| {r['scope']} | {r['job']} | {_num(r['salary_k'], 'K/月')} | {_num(r['previous_salary_k'], 'K/月')} | {_pct(r['qoq_pct'])} |")
    lines += ["", "### 个人目标岗位固定搜索", ""]
    searches = recruitment.get("search_summaries", [])
    if not searches:
        lines.append("尚未录入个人目标岗位快照。按月填写 `data/recruitment_searches.csv` 后，这里会显示 BOSS/智联/猎聘等固定搜索条件的职位数与薪资变化。")
    else:
        lines += ["| 平台 | 城市 | 关键词 | 日期 | 职位数 | 较上次 | 薪资中位数 | 较上次 |", "|---|---|---|---|---:|---:|---:|---:|"]
        for r in searches:
            lines.append(f"| {r['platform']} | {r['city']} | {r['keyword']} | {r['date'].isoformat()} | {_num(r['result_count'])} | {_pct(r['count_change_pct'])} | {_num(r['salary_median_k'], 'K/月')} | {_pct(r['salary_change_pct'])} |")
    return "\n".join(lines) + "\n"


def render_html(recruitment: dict[str, Any]) -> str:
    cards = []
    for r in recruitment.get("market_summaries", []):
        cards.append("<div class='card regional-card'>" f"<div class='muted'>{html.escape(r['scope'])} · {r['latest_period'].isoformat()}</div>" "<h3>招聘薪酬基准</h3>" f"<div class='score'>{_num(r['median_salary_k'], 'K/月')} {r['status_icon']}</div>" f"<div>同岗薪酬环比中位数 {_pct(r['median_qoq_pct'])}</div>" f"<div>上涨/下跌/持平 {r['up_count']}/{r['down_count']}/{r['flat_count']} · 热门岗位 {r['hot_job_count']}</div></div>")
    job_rows = []
    for r in recruitment.get("latest_jobs", []):
        job_rows.append("<tr>" f"<td>{html.escape(r['scope'])}</td><td>{html.escape(r['job'])}</td>" f"<td>{_num(r['salary_k'], 'K/月')}</td><td>{_num(r['previous_salary_k'], 'K/月')}</td><td>{_pct(r['qoq_pct'])}</td></tr>")
    searches = recruitment.get("search_summaries", [])
    if searches:
        search_rows = []
        for r in searches:
            search_rows.append("<tr>" f"<td>{html.escape(r['platform'])}</td><td>{html.escape(r['city'])}</td><td>{html.escape(r['keyword'])}</td>" f"<td>{r['date'].isoformat()}</td><td>{_num(r['result_count'])}</td><td>{_pct(r['count_change_pct'])}</td>" f"<td>{_num(r['salary_median_k'], 'K/月')}</td><td>{_pct(r['salary_change_pct'])}</td></tr>")
        search_html = "<h3>个人目标岗位固定搜索</h3><table><thead><tr><th>平台</th><th>城市</th><th>关键词</th><th>日期</th><th>职位数</th><th>较上次</th><th>薪资中位数</th><th>较上次</th></tr></thead>" + f"<tbody>{''.join(search_rows)}</tbody></table>"
    else:
        search_html = "<h3>个人目标岗位固定搜索</h3><p class='muted'>尚未录入个人目标岗位快照。按月填写 <code>data/recruitment_searches.csv</code> 后，这里会显示 BOSS/智联/猎聘等固定搜索条件的职位数与薪资变化，并自动生成“同岗招聘数量/同岗薪资中位数”指标。</p>"
    return "<section><h2>招聘市场</h2><p class='muted'>官方招聘薪酬基准用于判断外部就业市场，不直接计入家庭综合评分；个人固定搜索篮子有数据后会进入就业安全指标。</p>" + f"<div class='grid'>{''.join(cards)}</div>" + "<h3>热门岗位薪酬（最新季度）</h3><table><thead><tr><th>区域</th><th>岗位</th><th>本期</th><th>上期</th><th>环比</th></tr></thead>" + f"<tbody>{''.join(job_rows)}</tbody></table>{search_html}</section>"


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def enrich_reports(output_dir: str | Path, recruitment: dict[str, Any]) -> None:
    out = Path(output_dir)
    html_path = out / "index.html"
    md_path = out / "report.md"
    html_text = html_path.read_text(encoding="utf-8")
    marker = "<section><h2>核心指标</h2>"
    section = render_html(recruitment)
    html_text = html_text.replace(marker, section + marker, 1) if marker in html_text else html_text.replace("</main>", section + "</main>", 1)
    html_path.write_text(html_text, encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")
    md_marker = "\n## 核心指标"
    md_section = "\n" + render_markdown(recruitment).rstrip() + "\n"
    md_text = md_text.replace(md_marker, md_section + md_marker, 1) if md_marker in md_text else md_text + md_section
    md_path.write_text(md_text, encoding="utf-8")
    _write_csv(out / "recruitment_market_summary.csv", recruitment.get("market_summaries", []), ["scope", "latest_period", "previous_period", "hot_job_count", "median_salary_k", "median_qoq_pct", "up_count", "down_count", "flat_count", "comparable_count", "entrants", "exits", "status", "source_url"])
    _write_csv(out / "recruitment_latest_jobs.csv", recruitment.get("latest_jobs", []), ["scope", "period_end", "job", "salary_k", "previous_salary_k", "qoq_pct", "source_url"])
