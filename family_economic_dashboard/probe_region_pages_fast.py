from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from .probe_region_pages import SOURCES, fetch_text, pct


def probe(source: dict, collected_at: str) -> tuple[dict, list[dict[str, str]]]:
    region = source["region"]
    url = source["url"]
    try:
        text = fetch_text(url, timeout=10)
        parsed: dict[str, float] = {}
        rows: list[dict[str, str]] = []
        for indicator, patterns in source["metrics"].items():
            value = pct(text, patterns)
            if value is None:
                continue
            parsed[indicator] = value
            rows.append({
                "period": "2026-07",
                "cluster": source["cluster"],
                "region": region,
                "indicator": indicator,
                "value": f"{value:g}",
                "source_url": url,
                "collected_at": collected_at,
            })
        check = {
            "region": region,
            "cluster": source["cluster"],
            "kind": source["kind"],
            "url": url,
            "status": "ok",
            "text_length": len(text),
            "metrics_expected": sorted(source["metrics"]),
            "metrics_parsed": parsed,
            "sample": text[:220],
        }
        return check, rows
    except Exception as exc:
        return {
            "region": region,
            "cluster": source["cluster"],
            "kind": source["kind"],
            "url": url,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }, []


def main() -> None:
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    checks: list[dict] = []
    rows: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=9) as pool:
        futures = [pool.submit(probe, source, collected_at) for source in SOURCES]
        for future in as_completed(futures):
            check, part = future.result()
            checks.append(check)
            rows.extend(part)
            print(f"[{check['status']}] {check['region']} {check['kind']} parsed={check.get('metrics_parsed', {})} error={check.get('error', '')}")

    accessible = sorted({c["region"] for c in checks if c["status"] == "ok"})
    Path("data").mkdir(exist_ok=True)
    with Path("data/region_page_probe.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["period", "cluster", "region", "indicator", "value", "source_url", "collected_at"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["cluster"], r["region"], r["indicator"])))

    summary = {
        "collected_at": collected_at,
        "purpose": "GitHub Hosted Runner reachability and parser validation for regional official sources",
        "accessible_region_count": len(accessible),
        "accessible_regions": accessible,
        "metric_row_count": len(rows),
        "checks": sorted(checks, key=lambda c: (c["cluster"], c["region"], c["kind"])),
    }
    Path("data/region_page_probe_provenance.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not accessible:
        raise SystemExit("No provincial official source was accessible")
    print(f"Concurrent provincial probe complete: regions={len(accessible)}, metric_rows={len(rows)}")


if __name__ == "__main__":
    main()
