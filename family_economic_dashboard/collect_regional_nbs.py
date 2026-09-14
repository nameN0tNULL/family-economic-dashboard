from __future__ import annotations

import calendar
import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://data.stats.gov.cn"
META = "/dg/website/publicrelease/web/external/new"
STREAM = "/dg/website/publicrelease/web/external/stream/esData"
REFERER = f"{BASE}/dg/website/page.html#/pc/national/fsMonthData"
HEADERS = {
    "Origin": BASE,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": REFERER,
    "User-Agent": "family-economic-dashboard/1.0 Mozilla/5.0 Chrome/146.0.0.0 Safari/537.36",
}

ROOT_ID = "f4c6cd795fea436c807163397dd36b98"
SOURCE_URL = "https://data.stats.gov.cn/dg/website/page.html#/pc/national/fsMonthData"

REGIONS = [
    {"name": "北京市", "code": "110000000000", "cluster": "jing_jin_ji"},
    {"name": "天津市", "code": "120000000000", "cluster": "jing_jin_ji"},
    {"name": "河北省", "code": "130000000000", "cluster": "jing_jin_ji"},
    {"name": "上海市", "code": "310000000000", "cluster": "yangtze_river_delta"},
    {"name": "江苏省", "code": "320000000000", "cluster": "yangtze_river_delta"},
    {"name": "浙江省", "code": "330000000000", "cluster": "yangtze_river_delta"},
    {"name": "安徽省", "code": "340000000000", "cluster": "yangtze_river_delta"},
]

# UUIDs were discovered from the current NBS fsMonthData metadata tree. The collector
# validates the labels before use so a metadata change fails loudly instead of silently
# attaching the wrong series to an indicator name.
SERIES = {
    "industrial_growth": {
        "cid": "9593fb551802499683f758e0f6f45bc7",
        "indicator_id": "e2da5a05def84138b9d33828951adc59",
        "expected_label": "工业增加值累计增长",
        "unit": "%",
    },
    "fixed_asset_investment_growth": {
        "cid": "e43af1a71b2d4a768569866795ed66e2",
        "indicator_id": "31c20d4e16564c39a3e4d2cc0d2d83bb",
        "expected_label": "固定资产投资完成额累计增长",
        "unit": "%",
    },
}

FIELDS = [
    "date",
    "cluster",
    "region",
    "region_code",
    "indicator",
    "value",
    "unit",
    "source",
    "source_url",
    "collected_at",
    "note",
]


def get_json(path: str, params: dict[str, str]) -> dict:
    req = Request(f"{BASE}{path}?{urlencode(params)}", headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def post_json(body: dict) -> dict:
    req = Request(
        f"{BASE}{STREAM}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def validate_series(spec: dict) -> dict:
    payload = get_json(
        f"{META}/queryIndicatorsByCid",
        {"cid": spec["cid"], "dt": "", "name": ""},
    )
    items = payload.get("data", {}).get("list", [])
    item = next((x for x in items if str(x.get("_id", "")) == spec["indicator_id"]), None)
    if item is None:
        raise RuntimeError(f"NBS indicator UUID disappeared: {spec['indicator_id']}")
    label = str(item.get("i_showname", "")).strip()
    if spec["expected_label"] not in label:
        raise RuntimeError(
            f"NBS indicator label changed for {spec['indicator_id']}: expected {spec['expected_label']!r}, got {label!r}"
        )
    return {"label": label, "unit": str(item.get("du_name") or item.get("du") or spec["unit"])}


def latest_period(cid: str) -> str:
    payload = get_json(f"{META}/queryDtByCid", {"cid": cid, "rootId": ROOT_ID})
    token = str(payload.get("data", {}).get("dt_all", ""))
    if len(token) < 8 or not token[:6].isdigit():
        raise RuntimeError(f"Could not parse latest NBS month for cid={cid}: {token!r}")
    return token[:6]


def shift_month(yyyymm: str, delta: int) -> str:
    year = int(yyyymm[:4])
    month = int(yyyymm[4:6])
    index = year * 12 + month - 1 + delta
    return f"{index // 12:04d}{index % 12 + 1:02d}"


def month_end(yyyymm: str) -> str:
    year, month = int(yyyymm[:4]), int(yyyymm[4:6])
    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


def fetch_recent(spec: dict, latest: str) -> dict:
    start = shift_month(latest, -2)
    body = {
        "cid": spec["cid"],
        "indicatorIds": [spec["indicator_id"]],
        "daCatalogId": "",
        "das": [{"text": r["name"], "value": r["code"]} for r in REGIONS],
        "showType": 3,
        "dts": [f"{start}MM-{latest}MM"],
        "rootId": ROOT_ID,
    }
    payload = post_json(body)
    if payload.get("state") != 20000:
        raise RuntimeError(f"NBS stream request failed: {payload.get('state')} {payload.get('message')}")
    return payload


def parse_rows(indicator: str, spec: dict, payload: dict, collected_at: str) -> list[dict[str, str]]:
    cluster_by_code = {r["code"]: r["cluster"] for r in REGIONS}
    region_by_code = {r["code"]: r["name"] for r in REGIONS}
    rows: list[dict[str, str]] = []
    for block in payload.get("data", []):
        period = str(block.get("code", ""))[:6]
        if len(period) != 6 or not period.isdigit():
            continue
        for item in block.get("values", []):
            code = str(item.get("areaCode") or item.get("da_value") or "")
            value = str(item.get("value", "")).strip()
            if code not in cluster_by_code or not value:
                continue
            rows.append(
                {
                    "date": month_end(period),
                    "cluster": cluster_by_code[code],
                    "region": str(item.get("area") or region_by_code[code]),
                    "region_code": code,
                    "indicator": indicator,
                    "value": value,
                    "unit": str(item.get("du_name") or spec["unit"]),
                    "source": "国家统计局-分省月度数据",
                    "source_url": SOURCE_URL,
                    "collected_at": collected_at,
                    "note": "官方分省月度累计同比/累计增长口径；NBS stream/esData",
                }
            )
    return rows


def read_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return [dict(row) for row in csv.DictReader(f)]


def write_upsert(path: Path, new_rows: list[dict[str, str]]) -> None:
    merged: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in read_existing(path):
        if row.get("date") and row.get("region_code") and row.get("indicator"):
            merged[(row["date"], row["region_code"], row["indicator"])] = row
    for row in new_rows:
        merged[(row["date"], row["region_code"], row["indicator"])] = row
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])


def main() -> None:
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    all_rows: list[dict[str, str]] = []
    provenance: dict = {
        "collected_at": collected_at,
        "source": "国家统计局-分省月度数据",
        "endpoint": f"{BASE}{STREAM}",
        "root_id": ROOT_ID,
        "regions": REGIONS,
        "series": {},
        "notes": [
            "Current provincial retail-sales series is not available in NBS fsMonthData; retail remains a separate local-source fallback.",
            "The only retail child found under 国内贸易 is marked (-201012) and ends at 2010-12.",
        ],
    }

    for indicator, spec in SERIES.items():
        meta = validate_series(spec)
        latest = latest_period(spec["cid"])
        payload = fetch_recent(spec, latest)
        rows = parse_rows(indicator, spec, payload, collected_at)
        latest_nonblank = max((r["date"] for r in rows), default=None)
        regions_latest = sorted({r["region"] for r in rows if r["date"] == latest_nonblank}) if latest_nonblank else []
        provenance["series"][indicator] = {
            "cid": spec["cid"],
            "indicator_id": spec["indicator_id"],
            "label": meta["label"],
            "unit": meta["unit"],
            "latest_catalog_period": latest,
            "latest_nonblank_date": latest_nonblank,
            "regions_on_latest_nonblank_date": regions_latest,
            "rows_collected": len(rows),
        }
        all_rows.extend(rows)
        print(
            f"[ok] {indicator}: latest_catalog={latest}, latest_nonblank={latest_nonblank}, "
            f"regions={len(regions_latest)}, rows={len(rows)}"
        )

    if not all_rows:
        raise SystemExit("No regional NBS observations collected")

    write_upsert(Path("data/regional_observations.csv"), all_rows)
    Path("data/regional_provenance.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Collected/upserted {len(all_rows)} regional observations")


if __name__ == "__main__":
    main()
