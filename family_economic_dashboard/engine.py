from __future__ import annotations

import calendar
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

STATUS_SCORE = {"green": 100.0, "yellow": 65.0, "red": 30.0, "unknown": 50.0}
STATUS_ICON = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪"}


@dataclass(frozen=True)
class DashboardResult:
    as_of: date
    indicators: list[dict[str, Any]]
    dimensions: list[dict[str, Any]]
    overall_score: float
    overall_status: str
    resonance: list[dict[str, Any]]


def load_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_observations(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"date", "indicator", "value"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"observations missing required columns: {sorted(missing)}")
        for raw in reader:
            try:
                value = float(raw["value"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"non-numeric value for {raw.get('indicator')} on {raw.get('date')}") from exc
            rows.append(
                {
                    "date": datetime.strptime(raw["date"], "%Y-%m-%d").date(),
                    "indicator": raw["indicator"],
                    "value": value,
                    "note": raw.get("note", ""),
                }
            )
    rows.sort(key=lambda r: (r["indicator"], r["date"]))
    return rows


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


def _value_on_or_before(series: list[dict[str, Any]], when: date) -> tuple[float | None, date | None]:
    eligible = [r for r in series if r["date"] <= when]
    if not eligible:
        return None, None
    row = max(eligible, key=lambda r: r["date"])
    return float(row["value"]), row["date"]


def _evaluate_status(metric: dict[str, Any], current: float | None, yoy: float | None, six_month: float | None) -> str:
    if current is None:
        return "unknown"
    rule = metric.get("risk_rule", {})
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


def _overall_status(score: float) -> str:
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
        as_of_date = max(r["date"] for r in observations)

    rows: list[dict[str, Any]] = []
    for indicator_id, metric in indicators_cfg.items():
        series = [r for r in observations if r["indicator"] == indicator_id]
        current, current_date = _value_on_or_before(series, as_of_date)
        previous, previous_date = _value_on_or_before(series, _shift_months(as_of_date, -1))
        six_value, six_date = _value_on_or_before(series, _shift_months(as_of_date, -6))
        year_value, year_date = _value_on_or_before(series, _shift_months(as_of_date, -12))
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
                "current_date": current_date,
                "previous": previous,
                "previous_date": previous_date,
                "mom_pct": mom_pct,
                "six_month_value": six_value,
                "six_month_date": six_date,
                "six_month_pct": six_pct,
                "year_value": year_value,
                "year_date": year_date,
                "yoy_pct": yoy_pct,
                "status": status,
                "status_icon": STATUS_ICON[status],
                "score": STATUS_SCORE[status],
                "weight": float(metric.get("weight", 1.0)),
                "source": metric.get("source", ""),
            }
        )

    dimensions: list[dict[str, Any]] = []
    for dim in config["dimensions"]:
        subset = [r for r in rows if r["dimension"] == dim["id"]]
        denominator = sum(r["weight"] for r in subset)
        score = sum(r["score"] * r["weight"] for r in subset) / denominator if denominator else 50.0
        status = _overall_status(score)
        dimensions.append(
            {
                "dimension": dim["id"],
                "name": dim["name"],
                "weight": float(dim["weight"]),
                "score": round(score, 1),
                "status": status,
                "status_icon": STATUS_ICON[status],
                "red_count": sum(1 for r in subset if r["status"] == "red"),
                "yellow_count": sum(1 for r in subset if r["status"] == "yellow"),
            }
        )

    total_weight = sum(d["weight"] for d in dimensions)
    overall_score = round(sum(d["score"] * d["weight"] for d in dimensions) / total_weight, 1)
    overall_status = _overall_status(overall_score)

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

    return DashboardResult(as_of_date, rows, dimensions, overall_score, overall_status, resonance)
