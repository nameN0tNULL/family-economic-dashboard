from __future__ import annotations

import argparse
import calendar
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin
from urllib.request import Request, urlopen

USER_AGENT = "family-economic-dashboard/1.0 (+GitHub Actions; public statistics collector)"
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Observation:
    date: date
    indicator: str
    value: float
    note: str
    source_url: str


class LinkTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data: str) -> None:
        self.text_parts.append(data)
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href is not None:
            text = normalize("".join(self._parts))
            if text:
                self.links.append((self._href, text))
            self._href = None
            self._parts = []

    @property
    def text(self) -> str:
        return normalize(" ".join(self.text_parts))


def normalize(s: str) -> str:
    return SPACE_RE.sub(" ", s.replace("\xa0", " ")).strip()


def fetch_html(url: str, timeout: int = 30) -> str:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset()
    for encoding in [charset, "utf-8", "gb18030"]:
        if not encoding:
            continue
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    return raw.decode("utf-8", errors="replace")


def parse_page(html_text: str) -> LinkTextParser:
    parser = LinkTextParser()
    parser.feed(html_text)
    return parser


def discover_article(index_url: str, matcher: Callable[[str], bool]) -> tuple[str, str]:
    parser = parse_page(fetch_html(index_url))
    for href, text in parser.links:
        if matcher(text) and href and not href.lower().startswith(("javascript:", "#")):
            return urljoin(index_url, href), text
    raise RuntimeError(f"No matching article found at {index_url}")


def publication_year(text: str, title: str) -> int:
    m = re.search(r"(20\d{2})年", title)
    if m:
        return int(m.group(1))
    m = re.search(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日", text)
    if m:
        return int(m.group(1))
    raise ValueError("Could not determine publication year")


def period_end(title: str, text: str) -> date:
    year = publication_year(text, title)
    combined = f"{title} {text[:2500]}"
    m = re.search(r"1\s*[—－-]\s*(\d{1,2})\s*月(?:份)?", combined)
    if m:
        month = int(m.group(1))
    elif "前三季度" in combined:
        month = 9
    elif "上半年" in combined:
        month = 6
    elif "一季度" in combined:
        month = 3
    else:
        m = re.search(r"20\d{2}年\s*(\d{1,2})\s*月", title)
        if not m:
            m = re.search(r"(\d{1,2})\s*月份", title)
        if not m:
            raise ValueError(f"Could not determine data period from title: {title}")
        month = int(m.group(1))
    return date(year, month, calendar.monthrange(year, month)[1])


def signed(direction: str, number: str) -> float:
    value = float(number)
    return -value if direction in {"下降", "减少", "下跌"} else value


def extract_signed_pct(text: str, pattern: str) -> float:
    m = re.search(pattern, text)
    if not m:
        raise ValueError(f"Pattern did not match: {pattern}")
    return signed(m.group(1), m.group(2))


def amount_to_yi(direction: str, number: str, unit: str) -> float:
    value = float(number) * (10000.0 if unit == "万亿元" else 1.0)
    return -value if direction == "减少" else value


def collect_nbs_macro(index_url: str) -> tuple[list[Observation], dict]:
    url, title = discover_article(
        index_url,
        lambda t: "国民经济" in t and "统计公报" not in t and any(k in t for k in ("月份", "上半年", "运行", "发展态势")),
    )
    text = parse_page(fetch_html(url)).text
    d = period_end(title, text)
    obs = [
        Observation(d, "private_investment", extract_signed_pct(text, r"民间投资同比(增长|下降)([0-9.]+)%"), f"{title}；官方披露同比", url),
    ]
    m = re.search(r"(?:\d+月份，)?全国城镇调查失业率为([0-9.]+)%", text)
    if m:
        obs.append(Observation(d, "urban_unemployment_rate", float(m.group(1)), f"{title}；月度城镇调查失业率", url))
    return obs, {"source": "国家统计局-国民经济运行", "title": title, "url": url, "period": d.isoformat(), "indicators": [o.indicator for o in obs]}


def collect_nbs_profit(index_url: str) -> tuple[list[Observation], dict]:
    url, title = discover_article(index_url, lambda t: "规模以上工业企业利润" in t)
    text = parse_page(fetch_html(url)).text
    d = period_end(title, text)
    obs = [
        Observation(d, "private_profit", extract_signed_pct(text, r"私营企业实现利润总额[^。]*?同比(增长|下降)([0-9.]+)%"), f"{title}；私营工业企业利润同比", url),
    ]
    m = re.search(r"应收账款平均回收期为([0-9.]+)天", text)
    if m:
        obs.append(Observation(d, "industrial_receivables_days", float(m.group(1)), f"{title}；规上工业应收账款平均回收期", url))
    return obs, {"source": "国家统计局-工业企业利润", "title": title, "url": url, "period": d.isoformat(), "indicators": [o.indicator for o in obs]}


def collect_mof(index_url: str) -> tuple[list[Observation], dict]:
    url, title = discover_article(index_url, lambda t: "财政收支情况" in t and "年" in t)
    text = parse_page(fetch_html(url)).text
    d = period_end(title, text)
    obs: list[Observation] = []
    m = re.search(r"地方一般公共预算本级收入[0-9.]+亿元，同比(增长|下降)([0-9.]+)%", text)
    if m:
        obs.append(Observation(d, "national_local_fiscal_revenue_yoy", signed(m.group(1), m.group(2)), f"{title}；全国地方一般公共预算本级收入同比", url))
    m = re.search(r"国有土地使用权出让收入[0-9.]+亿元，同比(增长|下降)([0-9.]+)%", text)
    if m:
        obs.append(Observation(d, "national_land_sale_revenue_yoy", signed(m.group(1), m.group(2)), f"{title}；全国国有土地使用权出让收入同比", url))
    if not obs:
        raise ValueError("MOF page found but target fiscal metrics were not parsed")
    return obs, {"source": "财政部-全国财政收支", "title": title, "url": url, "period": d.isoformat(), "indicators": [o.indicator for o in obs]}


def collect_pbc(index_url: str) -> tuple[list[Observation], dict]:
    url, title = discover_article(index_url, lambda t: "金融统计数据报告" in t)
    text = parse_page(fetch_html(url)).text
    d = period_end(title, text)
    obs: list[Observation] = []
    hh = re.search(r"住户(?:部门)?贷款(?:增加|减少)[^。；]*?中长期贷款(增加|减少)([0-9.]+)(万亿元|亿元)", text)
    corp = re.search(r"企(?:（事）|\(事\))业单位贷款(?:增加|减少)[^。；]*?中长期贷款(增加|减少)([0-9.]+)(万亿元|亿元)", text)
    if hh:
        obs.append(Observation(d, "household_long_term_loans", amount_to_yi(hh.group(1), hh.group(2), hh.group(3)), f"{title}；年内累计新增，统一换算为亿元", url))
    if corp:
        obs.append(Observation(d, "corp_long_term_loans", amount_to_yi(corp.group(1), corp.group(2), corp.group(3)), f"{title}；年内累计新增，统一换算为亿元", url))
    if not obs:
        raise ValueError("PBC page found but long-term loan metrics were not parsed")
    return obs, {"source": "中国人民银行-金融统计数据报告", "title": title, "url": url, "period": d.isoformat(), "indicators": [o.indicator for o in obs]}


def read_existing(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return [dict(r) for r in csv.DictReader(f) if r.get("date") and r.get("indicator")]


def write_observations(path: Path, observations: list[Observation], collected_at: str) -> None:
    rows = read_existing(path)
    merged: dict[tuple[str, str], dict[str, str]] = {(r["date"], r["indicator"]): r for r in rows}
    for o in observations:
        merged[(o.date.isoformat(), o.indicator)] = {
            "date": o.date.isoformat(),
            "indicator": o.indicator,
            "value": f"{o.value:.6f}".rstrip("0").rstrip("."),
            "note": o.note,
            "source_url": o.source_url,
            "collected_at": collected_at,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "indicator", "value", "note", "source_url", "collected_at"])
        writer.writeheader()
        for key in sorted(merged):
            writer.writerow(merged[key])


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public official statistics")
    parser.add_argument("--sources", default="config/sources.json")
    parser.add_argument("--output", default="data/official_observations.csv")
    parser.add_argument("--provenance", default="data/provenance.json")
    args = parser.parse_args()

    cfg = json.loads(Path(args.sources).read_text(encoding="utf-8"))
    collected_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    jobs = [
        ("nbs_macro", collect_nbs_macro, cfg["nbs_index"]),
        ("nbs_profit", collect_nbs_profit, cfg["nbs_index"]),
        ("mof", collect_mof, cfg["mof_index"]),
        ("pbc", collect_pbc, cfg["pbc_index"]),
    ]
    all_obs: list[Observation] = []
    sources: list[dict] = []
    errors: list[dict] = []
    for name, fn, url in jobs:
        try:
            obs, prov = fn(url)
            all_obs.extend(obs)
            sources.append(prov)
            print(f"[ok] {name}: " + ", ".join(f"{o.indicator}={o.value:g}" for o in obs))
        except Exception as exc:
            errors.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[warn] {name}: {type(exc).__name__}: {exc}", file=sys.stderr)

    if not all_obs:
        raise SystemExit("No official observations were collected")
    write_observations(Path(args.output), all_obs, collected_at)
    provenance = {"collected_at": collected_at, "sources": sources, "errors": errors, "observation_count": len(all_obs)}
    Path(args.provenance).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(all_obs)} observations from {len(sources)} sources; errors={len(errors)}")


if __name__ == "__main__":
    main()
