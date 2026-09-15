from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://data.stats.gov.cn"
META = "/dg/website/publicrelease/web/external/new"
STREAM = "/dg/website/publicrelease/web/external/stream/esData"
PAGE = "mainYearData"
CODE = "8"
HEADERS = {
    "Origin": BASE,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": f"{BASE}/dg/website/page.html#/pc/national/{PAGE}",
    "User-Agent": "family-economic-dashboard/1.0 Mozilla/5.0 Chrome/146.0.0.0 Safari/537.36",
}

TARGET_CITIES = {
    "北京": ["110000", "110100"],
    "天津": ["120000", "120100"],
    "上海": ["310000", "310100"],
    "南京": ["320100"],
    "杭州": ["330100"],
    "宁波": ["330200"],
    "合肥": ["340100"],
    "广州": ["440100"],
    "深圳": ["440300"],
    "惠州": ["441300"],
    "武汉": ["420100"],
    "长沙": ["430100"],
    "南昌": ["360100"],
    "重庆": ["500000", "500100"],
    "成都": ["510100"],
}
KEYWORDS = ("常住人口", "年末人口", "人口")


def get_json(path: str, params: dict[str, str]) -> dict:
    req = Request(f"{BASE}{path}?{urlencode(params)}", headers=HEADERS)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def post_json(body: dict) -> dict:
    req = Request(
        f"{BASE}{STREAM}", data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=HEADERS, method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def root() -> dict:
    nodes = get_json(f"{META}/queryIndexTreeAsync", {"pid": "", "code": CODE}).get("data", [])
    if not nodes:
        raise RuntimeError("No mainYearData root")
    return nodes[0]


def children(pid: str) -> list[dict]:
    return get_json(f"{META}/queryIndexTreeAsync", {"pid": pid, "code": CODE}).get("data", [])


def indicators(cid: str) -> list[dict]:
    return get_json(f"{META}/queryIndicatorsByCid", {"cid": cid, "dt": "", "name": ""}).get("data", {}).get("list", [])


def dates(cid: str, root_id: str) -> dict:
    return get_json(f"{META}/queryDtByCid", {"cid": cid, "rootId": root_id}).get("data", {})


def fetch_values(root_id: str, cid: str, indicator_id: str, year: str) -> dict:
    das = []
    for city, codes in TARGET_CITIES.items():
        for code in codes:
            das.append({"text": city, "value": code})
    body = {
        "cid": cid,
        "indicatorIds": [indicator_id],
        "daCatalogId": "",
        "das": das,
        "showType": 3,
        "dts": [f"{year}AA-{year}AA"],
        "rootId": root_id,
    }
    return post_json(body)


def scan() -> dict:
    r = root()
    root_id = str(r.get("_id", ""))
    queue = deque([(r, [str(r.get("name", "主要城市年度数据"))], 0)])
    candidates: list[dict] = []
    visited = 0
    while queue and visited < 220:
        node, path, depth = queue.popleft()
        visited += 1
        cid = str(node.get("_id", ""))
        name = str(node.get("name", ""))
        if depth <= 4 and cid:
            try:
                inds = indicators(cid)
            except Exception:
                inds = []
            matching = []
            for item in inds:
                label = str(item.get("i_showname", "")).strip()
                if any(k in label for k in KEYWORDS):
                    matching.append({
                        "id": str(item.get("_id", "")),
                        "label": label,
                        "unit": str(item.get("du_name") or item.get("du") or ""),
                    })
            if matching:
                try:
                    dt = dates(cid, root_id)
                except Exception as exc:
                    dt = {"error": f"{type(exc).__name__}: {exc}"}
                candidates.append({"cid": cid, "node": name, "path": path, "indicators": matching, "dates": dt})
        if depth < 4 and cid:
            try:
                for child in children(cid):
                    queue.append((child, path + [str(child.get("name", ""))], depth + 1))
            except Exception:
                pass

    attempts = []
    for cand in candidates[:20]:
        dt_token = str(cand.get("dates", {}).get("dt_all", ""))
        year = dt_token[:4] if len(dt_token) >= 4 and dt_token[:4].isdigit() else "2025"
        for ind in cand["indicators"]:
            try:
                payload = fetch_values(root_id, cand["cid"], ind["id"], year)
                values = []
                for block in payload.get("data", []):
                    for item in block.get("values", []):
                        value = str(item.get("value", "")).strip()
                        if value:
                            values.append({
                                "area": str(item.get("area") or ""),
                                "areaCode": str(item.get("areaCode") or item.get("da_value") or ""),
                                "value": value,
                                "unit": str(item.get("du_name") or ind["unit"]),
                            })
                attempts.append({
                    "cid": cand["cid"], "node": cand["node"], "indicator": ind,
                    "year": year, "state": payload.get("state"), "values": values,
                })
            except Exception as exc:
                attempts.append({
                    "cid": cand["cid"], "node": cand["node"], "indicator": ind,
                    "year": year, "error": f"{type(exc).__name__}: {exc}",
                })
    return {
        "root_id": root_id,
        "root_name": r.get("name"),
        "visited_nodes": visited,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "attempts": attempts,
        "target_cities": TARGET_CITIES,
    }


def main() -> None:
    result = scan()
    output = {
        "collected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": "Find a stable NBS mainYearData population indicator and city-code mapping for the city vitality layer.",
        **result,
    }
    Path("data/city_population_nbs_probe.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    nonblank = sum(len(x.get("values", [])) for x in result["attempts"])
    print(f"NBS city population probe: candidates={result['candidate_count']}, nonblank_values={nonblank}")


if __name__ == "__main__":
    main()
