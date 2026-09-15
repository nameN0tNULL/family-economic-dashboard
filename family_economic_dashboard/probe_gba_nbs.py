from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://data.stats.gov.cn"
META = "/dg/website/publicrelease/web/external/new"
HEADERS = {
    "Origin": BASE,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "User-Agent": "family-economic-dashboard/1.0 Mozilla/5.0 Chrome/146.0.0.0 Safari/537.36",
}

GBA_MAINLAND = ["广州市", "深圳市", "珠海市", "佛山市", "惠州市", "东莞市", "中山市", "江门市", "肇庆市"]
KEYWORDS = ("地区生产总值", "工业", "固定资产投资", "社会消费品零售", "就业", "人口")
PAGES = [
    {"name": "mainYearData", "code": "8", "label": "主要城市年度数据"},
    {"name": "gatMonthData", "code": "9", "label": "港澳台月度数据"},
]


def get_json(path: str, params: dict[str, str], page: str) -> dict:
    headers = dict(HEADERS)
    headers["Referer"] = f"{BASE}/dg/website/page.html#/pc/national/{page}"
    req = Request(f"{BASE}{path}?{urlencode(params)}", headers=headers)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def root(page: dict) -> dict:
    payload = get_json(
        f"{META}/queryIndexTreeAsync",
        {"pid": "", "code": page["code"]},
        page["name"],
    )
    nodes = payload.get("data", [])
    if not nodes:
        raise RuntimeError(f"No root for {page['name']}")
    return nodes[0]


def children(page: dict, pid: str) -> list[dict]:
    payload = get_json(
        f"{META}/queryIndexTreeAsync",
        {"pid": pid, "code": page["code"]},
        page["name"],
    )
    return payload.get("data", [])


def indicators(page: dict, cid: str) -> list[dict]:
    payload = get_json(
        f"{META}/queryIndicatorsByCid",
        {"cid": cid, "dt": "", "name": ""},
        page["name"],
    )
    return payload.get("data", {}).get("list", [])


def dates(page: dict, cid: str, root_id: str) -> dict:
    return get_json(
        f"{META}/queryDtByCid",
        {"cid": cid, "rootId": root_id},
        page["name"],
    ).get("data", {})


def areas_for_indicator(page: dict, indicator_id: str) -> list[dict]:
    tree = get_json(
        "/dg/website/publicrelease/web/external/getDaCatalogTreeByIndicatorCid",
        {"indicatorCid": indicator_id},
        page["name"],
    ).get("data", [])
    if not tree:
        return []
    da_cid = str(tree[0].get("_id") or tree[0].get("id") or "")
    if not da_cid:
        return []
    return get_json(
        "/dg/website/publicrelease/web/external/getDasByDaCatalogId",
        {"daCid": da_cid},
        page["name"],
    ).get("data", [])


def scan(page: dict) -> dict:
    r = root(page)
    root_id = str(r.get("_id", ""))
    queue = deque([(r, [str(r.get("name", page["label"]))], 0)])
    visited = 0
    candidates: list[dict] = []
    all_node_names: list[str] = []
    while queue and visited < 160:
        node, path, depth = queue.popleft()
        visited += 1
        name = str(node.get("name", ""))
        all_node_names.append(name)
        cid = str(node.get("_id", ""))
        if any(k in name for k in KEYWORDS):
            candidates.append({"cid": cid, "name": name, "path": path})
        if depth >= 3 or not cid:
            continue
        try:
            for child in children(page, cid):
                queue.append((child, path + [str(child.get("name", ""))], depth + 1))
        except Exception:
            continue

    enriched: list[dict] = []
    discovered_areas: dict[str, dict] = {}
    for cand in candidates[:30]:
        try:
            inds = indicators(page, cand["cid"])
        except Exception as exc:
            cand["indicator_error"] = f"{type(exc).__name__}: {exc}"
            enriched.append(cand)
            continue
        cand["indicators"] = [
            {
                "id": str(i.get("_id", "")),
                "label": str(i.get("i_showname", "")).strip(),
                "unit": str(i.get("du_name") or i.get("du") or ""),
            }
            for i in inds[:12]
        ]
        try:
            cand["dates"] = dates(page, cand["cid"], root_id)
        except Exception as exc:
            cand["dates_error"] = f"{type(exc).__name__}: {exc}"
        if inds:
            try:
                area_rows = areas_for_indicator(page, str(inds[0].get("_id", "")))
                area_names = []
                for a in area_rows:
                    area_name = str(a.get("show_name") or a.get("name_text") or "").strip()
                    area_value = str(a.get("name_value") or "")
                    if area_name:
                        area_names.append(area_name)
                        discovered_areas.setdefault(area_name, {"name": area_name, "value": area_value})
                cand["area_sample"] = area_names[:60]
            except Exception as exc:
                cand["areas_error"] = f"{type(exc).__name__}: {exc}"
        enriched.append(cand)

    area_names = sorted(discovered_areas)
    mainland_coverage = {city: city in discovered_areas for city in GBA_MAINLAND}
    hk_matches = [n for n in area_names if "香港" in n]
    macao_matches = [n for n in area_names if "澳门" in n or "澳門" in n]
    return {
        "page": page["name"],
        "label": page["label"],
        "root_id": root_id,
        "root_name": r.get("name"),
        "visited_nodes": visited,
        "candidate_count": len(candidates),
        "mainland_gba_city_coverage": mainland_coverage,
        "mainland_gba_covered_count": sum(mainland_coverage.values()),
        "hong_kong_area_matches": hk_matches,
        "macao_area_matches": macao_matches,
        "area_sample": area_names[:100],
        "candidate_nodes": enriched,
        "top_node_sample": all_node_names[:100],
    }


def main() -> None:
    results = []
    for page in PAGES:
        try:
            result = scan(page)
            result["status"] = "ok"
            print(
                f"[ok] {page['name']}: visited={result['visited_nodes']} candidates={result['candidate_count']} "
                f"gba_cities={result['mainland_gba_covered_count']}/9 hk={len(result['hong_kong_area_matches'])} "
                f"macao={len(result['macao_area_matches'])}"
            )
        except Exception as exc:
            result = {"page": page["name"], "status": "error", "error": f"{type(exc).__name__}: {exc}"}
            print(f"[error] {page['name']}: {result['error']}")
        results.append(result)
    output = {
        "collected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose": "Assess whether NBS can support an exact Greater Bay Area layer beyond the Guangdong proxy.",
        "target_mainland_cities": GBA_MAINLAND,
        "results": results,
    }
    Path("data/gba_nbs_probe.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
