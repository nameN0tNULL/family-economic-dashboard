from __future__ import annotations

import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://data.stats.gov.cn"
META = "/dg/website/publicrelease/web/external/new"
STREAM = "/dg/website/publicrelease/web/external/stream/esData"
PAGE_CODE = 4
REFERER = f"{BASE}/dg/website/page.html#/pc/national/fsMonthData"
HEADERS = {
    "Origin": BASE,
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": REFERER,
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
}
PROVINCES = [
    {"name": "北京市", "code": "110000000000", "cluster": "jing_jin_ji"},
    {"name": "天津市", "code": "120000000000", "cluster": "jing_jin_ji"},
    {"name": "河北省", "code": "130000000000", "cluster": "jing_jin_ji"},
    {"name": "上海市", "code": "310000000000", "cluster": "yangtze_river_delta"},
    {"name": "江苏省", "code": "320000000000", "cluster": "yangtze_river_delta"},
    {"name": "浙江省", "code": "330000000000", "cluster": "yangtze_river_delta"},
    {"name": "安徽省", "code": "340000000000", "cluster": "yangtze_river_delta"},
]
TARGETS = {
    "industrial_growth": {
        "branch": ["工业"],
        "node_terms": ["工业增加值"],
        "preferred_series": ["累计增长", "同比增长"],
    },
    "fixed_asset_investment_growth": {
        "branch": ["固定资产投资"],
        "node_terms": ["固定资产投资"],
        "preferred_series": ["累计增长", "同比增长"],
    },
    "retail_sales_growth": {
        "branch": ["国内贸易", "贸易"],
        "node_terms": ["社会消费品零售总额"],
        "preferred_series": ["累计增长", "同比增长"],
    },
}


def get_json(path: str, params: dict[str, str]) -> dict:
    url = f"{BASE}{path}?{urlencode(params)}"
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def post_json(path: str, body: dict) -> dict:
    req = Request(
        f"{BASE}{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urlopen(req, timeout=25) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def tree(pid: str) -> list[dict]:
    payload = get_json(f"{META}/queryIndexTreeAsync", {"pid": pid, "code": str(PAGE_CODE)})
    return payload.get("data", [])


def indicators(cid: str) -> list[dict]:
    payload = get_json(f"{META}/queryIndicatorsByCid", {"cid": cid, "dt": "", "name": ""})
    return payload.get("data", {}).get("list", [])


def node_score(name: str, terms: list[str]) -> int:
    score = 0
    for term in terms:
        if term in name:
            score += 10 + len(term)
    if "增长" in name or "增速" in name:
        score += 3
    return score


def crawl_branch(root_id: str, branch_hints: list[str], node_terms: list[str]) -> tuple[list[dict], list[dict]]:
    top = tree(root_id)
    starts = [n for n in top if any(h in str(n.get("name", "")) for h in branch_hints)]
    if not starts:
        starts = top

    queue = deque((n, 1, [str(n.get("name", ""))]) for n in starts)
    seen: set[str] = set()
    visited: list[dict] = []
    candidates: list[dict] = []
    while queue and len(visited) < 90:
        node, depth, path = queue.popleft()
        cid = str(node.get("_id") or node.get("id") or "")
        if not cid or cid in seen:
            continue
        seen.add(cid)
        name = str(node.get("name", ""))
        score = node_score(name, node_terms)
        snapshot = {"cid": cid, "name": name, "path": path, "depth": depth, "score": score}
        visited.append(snapshot)
        if score > 0:
            candidates.append(snapshot)
        if depth >= 5:
            continue
        try:
            children = tree(cid)
        except Exception:
            children = []
        for child in children:
            child_name = str(child.get("name", ""))
            queue.append((child, depth + 1, path + [child_name]))
        time.sleep(0.03)

    candidates.sort(key=lambda x: (x["score"], -x["depth"]), reverse=True)
    return candidates, visited


def pick_indicator(items: list[dict], preferred: list[str]) -> dict | None:
    normalized = []
    for item in items:
        label = str(item.get("i_showname", "")).strip()
        normalized.append((label, item))
    for wanted in preferred:
        for label, item in normalized:
            if wanted in label:
                return item
    for label, item in normalized:
        if "%" in label or "增长" in label:
            return item
    return normalized[0][1] if normalized else None


def resolve_target(root_id: str, cfg: dict) -> dict:
    candidates, visited = crawl_branch(root_id, cfg["branch"], cfg["node_terms"])
    attempts: list[dict] = []
    for candidate in candidates[:12]:
        try:
            items = indicators(candidate["cid"])
        except Exception as exc:
            attempts.append({**candidate, "indicator_error": f"{type(exc).__name__}: {exc}"})
            continue
        labels = [str(x.get("i_showname", "")).strip() for x in items]
        chosen = pick_indicator(items, cfg["preferred_series"])
        attempts.append({**candidate, "indicator_labels": labels[:12]})
        if chosen:
            return {
                "cid": candidate["cid"],
                "node_name": candidate["name"],
                "path": candidate["path"],
                "indicator_id": str(chosen.get("_id", "")),
                "indicator_label": str(chosen.get("i_showname", "")).strip(),
                "unit": str(chosen.get("du_name") or chosen.get("du") or ""),
                "candidate_attempts": attempts,
                "visited_count": len(visited),
            }
    raise RuntimeError(f"No usable indicator resolved; candidates={candidates[:8]}")


def fetch_values(root_id: str, resolved: dict, period: str = "202607") -> tuple[dict, list[dict]]:
    body = {
        "cid": resolved["cid"],
        "indicatorIds": [resolved["indicator_id"]],
        "daCatalogId": "",
        "das": [{"text": p["name"], "value": p["code"]} for p in PROVINCES],
        "showType": 3,
        "dts": [f"{period}MM-{period}MM"],
        "rootId": root_id,
    }
    payload = post_json(STREAM, body)
    rows: list[dict] = []
    cluster_by_code = {p["code"]: p["cluster"] for p in PROVINCES}
    cluster_by_name = {p["name"]: p["cluster"] for p in PROVINCES}
    for block in payload.get("data", []):
        block_code = str(block.get("code", ""))
        for value in block.get("values", []):
            area = str(value.get("area") or value.get("da_name") or "")
            area_code = str(value.get("areaCode") or value.get("da_value") or "")
            rows.append(
                {
                    "period": block_code or period,
                    "cluster": cluster_by_code.get(area_code, cluster_by_name.get(area, "")),
                    "region": area,
                    "region_code": area_code,
                    "value": value.get("value", ""),
                    "unit": value.get("du_name", resolved.get("unit", "")),
                    "indicator_label": value.get("i_showname") or value.get("_name") or resolved["indicator_label"],
                }
            )
    return payload, rows


def main() -> None:
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    roots = tree("")
    if not roots:
        raise SystemExit("NBS fsMonthData root was empty")
    root = roots[0]
    root_id = str(root.get("_id") or root.get("id"))
    root_name = str(root.get("name", ""))
    print(f"[root] {root_name} {root_id}")

    results: dict[str, dict] = {}
    flat_rows: list[dict] = []
    errors: list[dict] = []
    for key, cfg in TARGETS.items():
        try:
            resolved = resolve_target(root_id, cfg)
            payload, rows = fetch_values(root_id, resolved)
            state = payload.get("state")
            results[key] = {
                "resolved": resolved,
                "state": state,
                "message": payload.get("message"),
                "data_blocks": len(payload.get("data", [])),
                "rows": rows,
            }
            for row in rows:
                flat_rows.append({"indicator": key, **row})
            print(
                f"[ok] {key}: node={resolved['node_name']} series={resolved['indicator_label']} "
                f"state={state} rows={len(rows)}"
            )
        except Exception as exc:
            errors.append({"indicator": key, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[error] {key}: {type(exc).__name__}: {exc}")

    Path("data").mkdir(exist_ok=True)
    out = {
        "collected_at": collected_at,
        "page": "fsMonthData",
        "page_code": PAGE_CODE,
        "root_id": root_id,
        "root_name": root_name,
        "period_requested": "202607",
        "source_project_reference": "cclyfblink/nbs_fetcher",
        "results": results,
        "errors": errors,
    }
    Path("data/nbs_monthly_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path("data/nbs_monthly_probe_rows.json").write_text(
        json.dumps(flat_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    ok = sum(1 for r in results.values() if r.get("state") == 20000 and r.get("rows"))
    if ok == 0:
        raise SystemExit("NBS fsMonthData probe did not return any usable monthly series")
    print(f"NBS fsMonthData probe complete: indicators_ok={ok}/{len(TARGETS)}, rows={len(flat_rows)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
