from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE_URL = "https://data.stats.gov.cn/easyquery.htm"
LANDING_URL = "https://data.stats.gov.cn/easyquery.htm?cn=E0101"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36"

REGIONS = {
    "110000": ("jing_jin_ji", "北京"),
    "120000": ("jing_jin_ji", "天津"),
    "130000": ("jing_jin_ji", "河北"),
    "310000": ("yangtze_river_delta", "上海"),
    "320000": ("yangtze_river_delta", "江苏"),
    "330000": ("yangtze_river_delta", "浙江"),
    "340000": ("yangtze_river_delta", "安徽"),
}

INDICATOR_SPECS = {
    "industrial_growth": {
        "root": "A02",
        "must": ["工业", "增加值"],
        "prefer": ["增长速度", "累计", "同比"],
        "avoid": ["按经济类型", "三大门类", "分行业"],
    },
    "fixed_asset_investment_growth": {
        "root": "A04",
        "must": ["固定资产投资"],
        "prefer": ["增长", "累计", "同比"],
        "avoid": ["民间", "房地产", "资金来源", "分行业"],
    },
    "retail_sales": {
        "root": "A07",
        "must": ["社会消费品零售总额"],
        "prefer": ["累计", "绝对量", "总额"],
        "avoid": ["按经营地", "按消费类型", "限额以上"],
    },
}


@dataclass(frozen=True)
class Leaf:
    code: str
    name: str


class NBSClient:
    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))
        self._prime()

    def _request(self, url: str) -> bytes:
        req = Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json,text/plain,*/*",
                "Referer": LANDING_URL,
            },
        )
        with self.opener.open(req, timeout=self.timeout) as resp:
            return resp.read()

    def _prime(self) -> None:
        self._request(LANDING_URL)

    def json(self, params: dict[str, str]) -> object:
        url = BASE_URL + "?" + urlencode(params)
        raw = self._request(url)
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            raise RuntimeError(f"Empty NBS response for {params.get('m')}")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Non-JSON NBS response: {text[:180]!r}") from exc

    def tree(self, parent: str, dbcode: str = "fsyd") -> list[dict]:
        data = self.json(
            {
                "m": "getTree",
                "id": parent,
                "dbcode": dbcode,
                "wdcode": "zb",
                "k1": str(int(time.time() * 1000)),
            }
        )
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected tree response for {parent}: {type(data).__name__}")
        return [x for x in data if isinstance(x, dict)]

    def query(self, indicator_code: str, periods: str = "LAST13", dbcode: str = "fsyd") -> dict:
        data = self.json(
            {
                "m": "QueryData",
                "dbcode": dbcode,
                "rowcode": "reg",
                "colcode": "sj",
                "wds": json.dumps([{"wdcode": "zb", "valuecode": indicator_code}], ensure_ascii=False),
                "dfwds": json.dumps([{"wdcode": "sj", "valuecode": periods}], ensure_ascii=False),
                "k1": str(int(time.time() * 1000)),
            }
        )
        if not isinstance(data, dict) or "returndata" not in data:
            raise RuntimeError(f"Unexpected query response for {indicator_code}")
        return data


def discover_leaves(client: NBSClient, root: str, max_nodes: int = 250) -> list[Leaf]:
    leaves: list[Leaf] = []
    queue = [root]
    seen: set[str] = set()
    while queue and len(seen) < max_nodes:
        parent = queue.pop(0)
        if parent in seen:
            continue
        seen.add(parent)
        nodes = client.tree(parent)
        for node in nodes:
            code = str(node.get("id", "")).strip()
            name = str(node.get("name", "")).strip()
            if not code or not name:
                continue
            if node.get("isParent") is True:
                queue.append(code)
            else:
                leaves.append(Leaf(code, name))
    if not leaves:
        raise RuntimeError(f"No leaves discovered below {root}")
    return leaves


def choose_leaf(leaves: list[Leaf], spec: dict) -> Leaf:
    candidates = [leaf for leaf in leaves if all(term in leaf.name for term in spec["must"])]
    if not candidates:
        sample = "; ".join(f"{x.code}:{x.name}" for x in leaves[:20])
        raise RuntimeError(f"No indicator matched {spec['must']}; sample={sample}")

    def score(leaf: Leaf) -> tuple[int, int, int]:
        positive = sum(1 for term in spec["prefer"] if term in leaf.name)
        negative = sum(1 for term in spec["avoid"] if term in leaf.name)
        return (positive - 3 * negative, -len(leaf.name), -len(leaf.code))

    return max(candidates, key=score)


def parse_rows(payload: dict, indicator: str, leaf: Leaf, collected_at: str) -> list[dict[str, str]]:
    returndata = payload.get("returndata", {})
    datanodes = returndata.get("datanodes", []) if isinstance(returndata, dict) else []
    rows: list[dict[str, str]] = []
    for node in datanodes:
        if not isinstance(node, dict):
            continue
        data = node.get("data", {})
        if not isinstance(data, dict) or data.get("hasdata") is not True:
            continue
        dims = {str(x.get("wdcode")): str(x.get("valuecode")) for x in node.get("wds", []) if isinstance(x, dict)}
        reg = dims.get("reg")
        period = dims.get("sj")
        if reg not in REGIONS or not period:
            continue
        cluster, region_name = REGIONS[reg]
        value = data.get("data")
        if value is None:
            value = data.get("strdata")
        rows.append(
            {
                "period": period,
                "cluster": cluster,
                "region": region_name,
                "reg_code": reg,
                "indicator": indicator,
                "indicator_code": leaf.code,
                "indicator_name": leaf.name,
                "value": str(value),
                "source_url": f"{LANDING_URL}&reg={reg}&zb={leaf.code}",
                "collected_at": collected_at,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "period",
        "cluster",
        "region",
        "reg_code",
        "indicator",
        "indicator_code",
        "indicator_name",
        "value",
        "source_url",
        "collected_at",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["indicator"], r["period"], r["reg_code"])))


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe NBS province-monthly data for major economic clusters")
    parser.add_argument("--output", default="data/region_probe.csv")
    parser.add_argument("--provenance", default="data/region_probe_provenance.json")
    args = parser.parse_args()

    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    client = NBSClient()
    rows: list[dict[str, str]] = []
    selected: dict[str, dict[str, str]] = {}
    errors: list[dict[str, str]] = []

    for indicator, spec in INDICATOR_SPECS.items():
        try:
            leaves = discover_leaves(client, spec["root"])
            leaf = choose_leaf(leaves, spec)
            selected[indicator] = {"code": leaf.code, "name": leaf.name}
            payload = client.query(leaf.code)
            part = parse_rows(payload, indicator, leaf, collected_at)
            rows.extend(part)
            covered = sorted({r["region"] for r in part})
            print(f"[ok] {indicator}: {leaf.code} {leaf.name}; rows={len(part)}; regions={','.join(covered)}")
        except Exception as exc:
            errors.append({"indicator": indicator, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[warn] {indicator}: {type(exc).__name__}: {exc}")

    if not rows:
        raise SystemExit("Regional probe collected no observations")

    write_csv(Path(args.output), rows)
    latest_periods: dict[str, str] = {}
    for indicator in INDICATOR_SPECS:
        periods = [r["period"] for r in rows if r["indicator"] == indicator]
        if periods:
            latest_periods[indicator] = max(periods)

    provenance = {
        "collected_at": collected_at,
        "database": "国家统计局 国家数据 / 分省月度数据 (fsyd)",
        "landing_url": LANDING_URL,
        "clusters": {
            "jing_jin_ji": ["北京", "天津", "河北"],
            "yangtze_river_delta": ["上海", "江苏", "浙江", "安徽"],
        },
        "selected_indicators": selected,
        "latest_periods": latest_periods,
        "row_count": len(rows),
        "errors": errors,
    }
    Path(args.provenance).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Regional probe complete: rows={len(rows)}, indicators={len(selected)}, errors={len(errors)}")


if __name__ == "__main__":
    main()
