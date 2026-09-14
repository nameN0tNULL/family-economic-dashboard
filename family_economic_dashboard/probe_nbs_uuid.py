from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

API = "https://data.stats.gov.cn/dg/website/publicrelease/web/external/getEsDataByCidAndDt"
ROOT_ID = "c4d82af16c3d4f0cb4f09d4af7d5888e"
GDP_CID = "6f8fbd415cbc40ffa7ecb7fd917f2598"
PROVINCES = [
    ("北京市", "110000000000"),
    ("河北省", "130000000000"),
    ("上海市", "310000000000"),
    ("浙江省", "330000000000"),
    ("安徽省", "340000000000"),
]
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://data.stats.gov.cn/dg/website/page.html",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def fetch(province: str, code: str) -> dict:
    body = {
        "cid": GDP_CID,
        "daCatalogId": "",
        "das": [{"text": province, "value": code}],
        "showType": "1",
        "dts": ["2024YY-2024YY"],
        "rootId": ROOT_ID,
    }
    req = Request(API, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=HEADERS, method="POST")
    with urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        status = resp.status
        ctype = resp.headers.get("Content-Type", "")
    result = {"province": province, "http_status": status, "content_type": ctype, "body_sample": raw[:500]}
    try:
        payload = json.loads(raw)
        result["state"] = payload.get("state")
        result["data_blocks"] = len(payload.get("data", [])) if isinstance(payload, dict) else None
        if isinstance(payload, dict) and payload.get("data"):
            values = payload["data"][0].get("values", [])
            result["value_sample"] = [
                {"name": v.get("i_showname") or v.get("_name"), "unit": v.get("du_name"), "value": v.get("value")}
                for v in values[:5]
            ]
    except json.JSONDecodeError:
        result["json"] = False
    return result


def main() -> None:
    rows = []
    for province, code in PROVINCES:
        try:
            row = fetch(province, code)
            row["status"] = "ok"
            print(f"[ok] {province}: http={row.get('http_status')} state={row.get('state')} blocks={row.get('data_blocks')}")
        except Exception as exc:
            row = {"province": province, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            print(f"[error] {province}: {row['error']}")
        rows.append(row)
    out = {
        "collected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "endpoint": API,
        "source_project_reference": "Ayanya-0628/nbs-prov",
        "purpose": "Smoke-test the newer NBS UUID endpoint from GitHub Hosted Runner",
        "results": rows,
    }
    Path("data").mkdir(exist_ok=True)
    Path("data/nbs_uuid_probe.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not any(r.get("state") == 20000 for r in rows):
        raise SystemExit("NBS UUID endpoint did not return a successful state for any test province")


if __name__ == "__main__":
    main()
