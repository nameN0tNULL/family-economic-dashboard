from __future__ import annotations

import csv
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen

SOURCES = [
    {
        "period_end": "2025-12-31",
        "period": "2025Q4",
        "url": "https://www.calss.net.cn/p1/kybgList/20260224/44935.html",
        "source": "中国劳动和社会保障科学研究院",
    },
    {
        "period_end": "2026-03-31",
        "period": "2026Q1",
        "url": "https://www.mohrss.gov.cn/SYrlzyhshbzb/laodongguanxi_/fwyd/202607/t20260708_579828.html",
        "source": "人社部/中国劳动和社会保障科学研究院",
    },
]
SCOPES = {"京津冀", "长三角", "珠三角"}


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.tokens: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        cleaned = _clean(data)
        if cleaned:
            self.tokens.append(cleaned)
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def _clean(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\xa0", " ")).strip()


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 family-economic-dashboard/1.0"})
    with urlopen(req, timeout=30) as resp:
        body = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    for encoding in (charset, "utf-8", "gb18030"):
        try:
            return body.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


def _is_salary(value: str) -> bool:
    compact = value.replace(" ", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", compact):
        return False
    x = float(compact)
    return 0.1 <= x <= 10.0


def _parse_tables(parser: TableParser) -> list[tuple[str, str, float]]:
    result: list[tuple[str, str, float]] = []
    current_scope: str | None = None
    seen: set[tuple[str, str]] = set()
    for raw in parser.rows:
        cells = [_clean(x) for x in raw if _clean(x)]
        if not cells:
            continue
        job = salary_text = None
        if len(cells) >= 3:
            if cells[0] in SCOPES:
                current_scope = cells[0]
                job, salary_text = cells[1], cells[2]
            else:
                current_scope = None
                continue
        elif len(cells) == 2 and current_scope:
            job, salary_text = cells
        if not current_scope or not job or not salary_text or not _is_salary(salary_text):
            continue
        key = (current_scope, job)
        if key not in seen:
            seen.add(key)
            result.append((current_scope, job, float(salary_text.replace(" ", ""))))
    return result


def _parse_tokens(parser: TableParser) -> list[tuple[str, str, float]]:
    tokens = parser.tokens
    result: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()
    current_scope: str | None = None
    started = False
    for idx, token in enumerate(tokens):
        if "重点区域" in token and "岗位" in token:
            started = True
        if "重点行业" in token and started:
            current_scope = None
            break
        scope_hit = next((scope for scope in SCOPES if token == scope or token.endswith(scope)), None)
        if scope_hit:
            current_scope = scope_hit
            started = True
            continue
        if not started or not current_scope or not _is_salary(token) or idx == 0:
            continue
        job = tokens[idx - 1]
        if job in SCOPES or _is_salary(job) or any(x in job for x in ("单位", "季度", "平均招聘薪酬", "数字岗位名称")):
            continue
        key = (current_scope, job)
        if key not in seen:
            seen.add(key)
            result.append((current_scope, job, float(token.replace(" ", ""))))
    return result


def parse_market_rows(text: str) -> tuple[list[tuple[str, str, float]], str]:
    parser = TableParser()
    parser.feed(text)
    table_rows = _parse_tables(parser)
    if len(table_rows) >= 40:
        return table_rows, "html_table"
    token_rows = _parse_tokens(parser)
    return token_rows, "text_tokens"


def collect(output: str | Path = "data/recruitment_market.csv", provenance: str | Path = "data/recruitment_provenance.json") -> None:
    rows: list[dict[str, object]] = []
    source_meta: list[dict[str, object]] = []
    for source in SOURCES:
        text = fetch_text(source["url"])
        parsed, mode = parse_market_rows(text)
        if len(parsed) < 40:
            raise RuntimeError(f"Recruitment parse too small for {source['period']}: {len(parsed)} rows via {mode}")
        for scope, job, salary in parsed:
            rows.append({
                "period_end": source["period_end"],
                "period": source["period"],
                "scope_type": "region",
                "scope": scope,
                "job": job,
                "salary_wan_month": f"{salary:.2f}",
                "source": source["source"],
                "source_url": source["url"],
            })
        source_meta.append({**source, "rows": len(parsed), "scopes": sorted({x[0] for x in parsed}), "parse_mode": mode})

    rows.sort(key=lambda r: (str(r["period_end"]), str(r["scope"]), str(r["job"])))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["period_end", "period", "scope_type", "scope", "job", "salary_wan_month", "source", "source_url"])
        writer.writeheader(); writer.writerows(rows)
    Path(provenance).write_text(json.dumps({"sources": source_meta, "total_rows": len(rows)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(rows)} official recruitment salary rows")


if __name__ == "__main__":
    collect()
