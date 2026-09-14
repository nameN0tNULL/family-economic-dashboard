from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .collect import Observation, discover_article, fetch_html, parse_page, period_end, signed, write_observations


def collect(index_url: str) -> tuple[list[Observation], dict]:
    url, title = discover_article(index_url, lambda t: "规模以上工业企业利润" in t)
    text = parse_page(fetch_html(url)).text
    d = period_end(title, text)

    m = re.search(r"私营企业实现利润总额[^。]*?(?:同比)?(增长|下降)([0-9.]+)%", text)
    if not m:
        raise ValueError("Could not parse private enterprise profit growth")
    observations = [
        Observation(d, "private_profit", signed(m.group(1), m.group(2)), f"{title}；私营工业企业利润同比", url)
    ]

    m = re.search(r"应收账款平均回收期为([0-9.]+)天", text)
    if m:
        observations.append(
            Observation(d, "industrial_receivables_days", float(m.group(1)), f"{title}；规上工业应收账款平均回收期", url)
        )
    return observations, {
        "source": "国家统计局-工业企业利润",
        "title": title,
        "url": url,
        "period": d.isoformat(),
        "indicators": [o.indicator for o in observations],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect NBS industrial profit statistics")
    parser.add_argument("--sources", default="config/sources.json")
    parser.add_argument("--output", default="data/official_observations.csv")
    parser.add_argument("--provenance", default="data/provenance.json")
    args = parser.parse_args()

    cfg = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    observations, source = collect(cfg["nbs_index"])
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    write_observations(Path(args.output), observations, collected_at)

    provenance_path = Path(args.provenance)
    provenance = json.loads(provenance_path.read_text(encoding="utf-8")) if provenance_path.exists() else {"sources": [], "errors": []}
    provenance["sources"] = [x for x in provenance.get("sources", []) if x.get("source") != source["source"]] + [source]
    provenance["errors"] = [x for x in provenance.get("errors", []) if x.get("source") != "nbs_profit"]
    provenance["observation_count"] = int(provenance.get("observation_count", 0)) + len(observations)
    provenance["collected_at"] = collected_at
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[ok] nbs_profit_compat: " + ", ".join(f"{o.indicator}={o.value:g}" for o in observations))


if __name__ == "__main__":
    main()
