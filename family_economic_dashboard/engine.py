from __future__ import annotations

import calendar
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

STATUS_SCORE = {"green": 100.0, "yellow": 65.0, "red": 30.0, "unknown": 50.0}
STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}


@dataclass(frozen=True)
class DashboardResult:
    as_of: date
    indicators: list[dict[str, Any]]
    dimensions: list[dict[str, Any]]
    overall_score: float | None
    overall_status: str
    overall_coverage: float
    resonance: list[dict[str, Any]]


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_observations(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    p = Path(path)
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"date", "indicator", "value"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"observations missing required columns: {sorted(missing)}")
        for raw in reader:
            if not raw.get("date") or not raw.get("indicator") or raw.get("value") in (None, ""):
                continue
            try:
                value = float(raw["value"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"non-numeric value for {raw.get('indicator')} on {raw.get('date')}") from exc
            row: dict[str, Any] = dict(raw)
            row.update(
                {
                    "date": datetime.strptime(raw["date"], "%Y-%m-%d").date(),
                    "indicator": raw["indicator"],
                    "value": value,
                    "note": raw.get("note", ""),
                    "source_url": raw.get("source_url", ""),
                }
            )
            rows.append(row)
    rows.sort(key=lambda r: (r["indicator"], r["date"]))
    return rows


def merge_observations(groups: Iterable[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge sources by (date, indicator); later groups override earlier groups."""
    merged: dict[tuple[date, str], dict[str, Any]] = {}
    for rows in groups:
        for row in rows:
            merged[(row["date"], row["indicator"])] = row
    return sorted(merged.values(), key=lambda r: (r["indicator"], r["date"]))


def _shift_months(d: date, months: int) -> date:
    index = d.year * 12 + (d.month - 1) + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current / previous - 1.0) * 100.0


def _row_on_or_before(series: list[dict[str, Any]], when: date) -> dict[str, Any] | None:
    eligible = [r for r in series if r["date"] <= when]
    return max(eligible, key=lambda r: r["date"]) if eligible else None


def _evaluate_status(metric: dict[str, Any], current: float | None, yoy: float | None, six_month: float | None) -> str:
    if current is None:
        return "unknown"
    rule = metric.get("risk_rule")
    if not rule:
        return "unknown"
    basis = rule.get("basis", "yoy_pct")
    x = current if basis == "absolute" else six_month if basis == "six_month_pct" else yoy
    if x is None:
        return "unknown"
    direction = rule.get("risk_direction", "lower_is_worse")
    yellow = float(rule["yellow"])
    red = float(rule["red"])
    if direction == "higher_is_worse":
        return "red" if x >= red else "yellow" if x >= yellow else "green"
    return "red" if x <= red else "yellow" if x <= yellow else "green"


def _overall_status(score: float | None) -> str:
    if score is None:
        return "unknown"
    return "green" if score >= 80 else "yellow" if score >= 60 else "red"


def calculate_dashboard(config: dict[str, Any], observations: list[dict[str, Any]], as_of: str | date | None = None) -> DashboardResult:
    indicators_cfg = {x["id"]: x for x in config["indicators"]}
    unknown = sorted({r["indicator"] for r in observations} - set(indicators_cfg))
    if unknown:
        raise ValueError(f"observations contain unknown indicators: {unknown}")

    if isinstance(as_of, str):
        as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
    elif isinstance(as_of, date):
        as_of_date = as_of
    else:
        as_of_date = max((r["date"] for r in observations), default=date.today())

    rows: list[dict[str, Any]] = []
    for indicator_id, metric in indicators_cfg.items():
        series = [r for r in observations if r["indicator"] == indicator_id]
        current_row = _row_on_or_before(series, as_of_date)
        previous_row = _row_on_or_before(series, _shift_months(as_of_date, -1))
        six_row = _row_on_or_before(series, _shift_months(as_of_date, -6))
        year_row = _row_on_or_before(series, _shift_months(as_of_date, -12))
        current = float(current_row["value"]) if current_row else None
        previous = float(previous_row["value"]) if previous_row else None
        six_value = float(six_row["value"]) if six_row else None
        year_value = float(year_row["value"]) if year_row else None
        mom_pct = _pct_change(current, previous)
        six_pct = _pct_change(current, six_value)
        yoy_pct = _pct_change(current, year_value)
        status = _evaluate_status(metric, current, yoy_pct, six_pct)
        rows.append(
            {
                "indicator": indicator_id,
                "name": metric["name"],
                "dimension": metric["dimension"],
                "frequency": metric["frequency"],
                "unit": metric.get("unit", ""),
                "current": current,
                "current_date": current_row["date"] if current_row else None,
                "previous": previous,
                "previous_date": previous_row["date"] if previous_row else None,
                "mom_pct": mom_pct,
                "six_month_value": six_value,
                "six_month_date": six_row["date"] if six_row else None,
                "six_month_pct": six_pct,
                "year_value": year_value,
                "year_date": year_row["date"] if year_row else None,
                "yoy_pct": yoy_pct,
                "status": status,
                "status_icon": STATUS_ICON[status],
                "score": STATUS_SCORE[status],
                "weight": float(metric.get("weight", 1.0)),
                "source": metric.get("source", ""),
                "collection": metric.get("collection", "manual"),
                "note": current_row.get("note", "") if current_row else "",
                "source_url": current_row.get("source_url", "") if current_row else "",
            }
        )

    dimensions: list[dict[str, Any]] = []
    for dim in config["dimensions"]:
        subset = [r for r in rows if r["dimension"] == dim["id"] and r["weight"] > 0]
        known = [r for r in subset if r["status"] != "unknown"]
        possible_weight = sum(r["weight"] for r in subset)
        known_weight = sum(r["weight"] for r in known)
        score = (
            round(sum(r["score"] * r["weight"] for r in known) / known_weight, 1)
            if known_weight
            else None
        )
        status = _overall_status(score)
        dimensions.append(
            {
                "dimension": dim["id"],
                "name": dim["name"],
                "weight": float(dim["weight"]),
                "score": score,
                "status": status,
                "status_icon": STATUS_ICON[status],
                "red_count": sum(1 for r in known if r["status"] == "red"),
                "yellow_count": sum(1 for r in known if r["status"] == "yellow"),
                "known_count": len(known),
                "total_count": len(subset),
                "coverage": round(known_weight / possible_weight * 100.0, 1) if possible_weight else 0.0,
            }
        )

    scored_dims = [d for d in dimensions if d["score"] is not None and d["weight"] > 0 and d["coverage"] > 0]
    effective_weights = {d["dimension"]: d["weight"] * d["coverage"] / 100.0 for d in scored_dims}
    scored_weight = sum(effective_weights.values())
    total_dim_weight = sum(d["weight"] for d in dimensions if d["weight"] > 0)
    overall_score = (
        round(sum(float(d["score"]) * effective_weights[d["dimension"]] for d in scored_dims) / scored_weight, 1)
        if scored_weight
        else None
    )
    overall_status = _overall_status(overall_score)
    overall_coverage = round(
        sum(d["coverage"] * d["weight"] for d in dimensions if d["weight"] > 0) / total_dim_weight,
        1,
    ) if total_dim_weight else 0.0

    resonance: list[dict[str, Any]] = []
    rcfg = config.get("resonance", {"watch": 2, "risk": 3})
    for dim in dimensions:
        red_count = dim["red_count"]
        if red_count >= int(rcfg.get("risk", 3)):
            level = "risk"
        elif red_count >= int(rcfg.get("watch", 2)):
            level = "watch"
        else:
            continue
        resonance.append({"dimension": dim["dimension"], "name": dim["name"], "red_count": red_count, "level": level})

    return DashboardResult(as_of_date, rows, dimensions, overall_score, overall_status, overall_coverage, resonance)
