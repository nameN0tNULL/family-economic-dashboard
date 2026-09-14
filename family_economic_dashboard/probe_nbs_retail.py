from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .probe_nbs_monthly import META, PROVINCES, STREAM, get_json, post_json, tree


def indicator_items(cid: str) -> list[dict]:
    payload = get_json(f"{META}/queryIndicatorsByCid", {"cid": cid, "dt": "", "name": ""})
    return payload.get("data", {}).get("list", [])


def dates(cid: str, root_id: str) -> dict:
    return get_json(f"{META}/queryDtByCid", {"cid": cid, "rootId": root_id})


def fetch_one(root_id: str, cid: str, indicator_id: str, period: str = "202607") -> dict:
    return post_json(
        STREAM,
        {
            "cid": cid,
            "indicatorIds": [indicator_id],
            "daCatalogId": "",
            "das": [{"text": p["name"], "value": p["code"]} for p in PROVINCES],
            "showType": 3,
            "dts": [f"{period}MM-{period}MM"],
            "rootId": root_id,
        },
    )


def main() -> None:
    roots = tree("")
    root = roots[0]
    root_id = str(root.get("_id") or root.get("id"))
    top = tree(root_id)
    trade = next((x for x in top if "国内贸易" in str(x.get("name", ""))), None)
    if trade is None:
        raise SystemExit("No 国内贸易 branch found")

    nodes = [trade]
    trade_id = str(trade.get("_id") or trade.get("id"))
    nodes.extend(tree(trade_id))
    checks: list[dict] = []
    successful: list[dict] = []

    for node in nodes:
        cid = str(node.get("_id") or node.get("id") or "")
        name = str(node.get("name", ""))
        try:
            items = indicator_items(cid)
            dt = dates(cid, root_id)
        except Exception as exc:
            checks.append({"node": name, "cid": cid, "error": f"{type(exc).__name__}: {exc}"})
            continue

        entry = {
            "node": name,
            "cid": cid,
            "indicators": [
                {
                    "id": str(i.get("_id", "")),
                    "label": str(i.get("i_showname", "")).strip(),
                    "unit": str(i.get("du_name") or i.get("du") or ""),
                }
                for i in items
            ],
            "dates_response": dt,
        }
        checks.append(entry)

        for item in items:
            label = str(item.get("i_showname", "")).strip()
            if "社会消费品零售总额" not in label:
                continue
            if "累计增长" not in label and "同比增长" not in label:
                continue
            payload = fetch_one(root_id, cid, str(item.get("_id", "")))
            values = []
            for block in payload.get("data", []):
                for value in block.get("values", []):
                    values.append(
                        {
                            "period": block.get("code"),
                            "area": value.get("area"),
                            "areaCode": value.get("areaCode"),
                            "value": value.get("value"),
                            "label": value.get("i_showname") or label,
                        }
                    )
            successful.append(
                {
                    "node": name,
                    "cid": cid,
                    "indicator_id": str(item.get("_id", "")),
                    "indicator_label": label,
                    "state": payload.get("state"),
                    "message": payload.get("message"),
                    "values": values,
                    "non_blank": sum(1 for v in values if str(v.get("value", "")).strip()),
                }
            )

    out = {
        "collected_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root_id": root_id,
        "trade_branch": {"name": str(trade.get("name", "")), "cid": trade_id},
        "checks": checks,
        "fetch_attempts": successful,
    }
    Path("data/nbs_retail_probe.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not successful:
        raise SystemExit("No retail growth indicator found under 国内贸易")


if __name__ == "__main__":
    main()
