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
        "url": "https://www.calss.net.cn/p1/kybgList/20260515/45341.html",
        "source": "中国劳动和社会保障科学研究院",
        "image_url": "https://www.calss.net.cn/u/cms/www/202605/15131524or4i.jpg",
    },
]
SCOPES = {"京津冀", "长三角", "珠三角"}

# The 2026Q1 official CALSS release stores the regional table as an image rather
# than an HTML table. Keep a reviewed transcription in code so CI stays
# deterministic and does not depend on OCR. The source page and official image
# URL remain recorded in provenance and are checked for reachability each run.
VERIFIED_SNAPSHOTS: dict[str, list[tuple[str, str, float]]] = {
    "2026Q1": [
        ("京津冀", "新媒体运营", 0.82),
        ("京津冀", "短视频运营", 0.77),
        ("京津冀", "电气工程师", 1.12),
        ("京津冀", "Java开发工程师", 1.81),
        ("京津冀", "运维工程师", 0.99),
        ("京津冀", "国内电商运营", 0.87),
        ("京津冀", "产品经理", 1.69),
        ("京津冀", "前端开发工程师", 1.44),
        ("京津冀", "算法工程师", 2.14),
        ("京津冀", "网络销售员", 1.03),
        ("京津冀", "嵌入式软件开发工程师", 1.72),
        ("京津冀", "C/C++开发工程师", 2.06),
        ("京津冀", "设备维护工程师", 0.75),
        ("京津冀", "自动化工程师", 0.95),
        ("京津冀", "网络工程师", 1.10),
        ("京津冀", "Python开发工程师", 1.64),
        ("京津冀", "数据开发工程师", 1.38),
        ("京津冀", "C#开发工程师", 1.50),
        ("长三角", "电气工程师", 1.24),
        ("长三角", "新媒体运营", 0.89),
        ("长三角", "Java开发工程师", 1.89),
        ("长三角", "国内电商运营", 0.94),
        ("长三角", "运维工程师", 1.07),
        ("长三角", "前端开发工程师", 1.46),
        ("长三角", "嵌入式软件开发工程师", 1.95),
        ("长三角", "产品经理", 1.72),
        ("长三角", "算法工程师", 2.19),
        ("长三角", "硬件工程师", 1.69),
        ("长三角", "设备维护工程师", 1.04),
        ("长三角", "自动化工程师", 0.97),
        ("长三角", "网络工程师", 1.08),
        ("长三角", "C#开发工程师", 1.53),
        ("长三角", "硬件测试工程师", 1.11),
        ("长三角", "CAD设计/制图工程师", 0.81),
        ("长三角", "电子/电器维修/保养工程师", 0.93),
        ("珠三角", "新媒体运营", 0.82),
        ("珠三角", "电气工程师", 1.20),
        ("珠三角", "国内电商运营", 0.87),
        ("珠三角", "硬件工程师", 1.63),
        ("珠三角", "Java开发工程师", 1.87),
        ("珠三角", "运维工程师", 1.11),
        ("珠三角", "短视频运营", 0.84),
        ("珠三角", "嵌入式软件开发工程师", 1.91),
        ("珠三角", "产品经理", 1.79),
        ("珠三角", "前端开发工程师", 1.45),
        ("珠三角", "网络销售员", 0.94),
        ("珠三角", "自动化工程师", 1.05),
        ("珠三角", "设备维护工程师", 0.99),
        ("珠三角", "数据分析师", 1.21),
    ]
}


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


def check_url(url: str) -> None:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 family-economic-dashboard/1.0"})
    with urlopen(req, timeout=30) as resp:
        if getattr(resp, "status", 200) >= 400:
            raise RuntimeError(f"HTTP {resp.status} for {url}")


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
    if len(token_rows) >= 40:
        return token_rows, "text_tokens"
    return [], "not_machine_readable"


def collect(output: str | Path = "data/recruitment_market.csv", provenance: str | Path = "data/recruitment_provenance.json") -> None:
    rows: list[dict[str, object]] = []
    source_meta: list[dict[str, object]] = []
    for source in SOURCES:
        text = fetch_text(source["url"])
        parsed, mode = parse_market_rows(text)
        if len(parsed) < 40 and source["period"] in VERIFIED_SNAPSHOTS:
            if source.get("image_url"):
                check_url(str(source["image_url"]))
            parsed = list(VERIFIED_SNAPSHOTS[source["period"]])
            mode = "verified_official_image_snapshot"
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
        source_meta.append({
            **source,
            "rows": len(parsed),
            "scopes": sorted({x[0] for x in parsed}),
            "parse_mode": mode,
        })

    rows.sort(key=lambda r: (str(r["period_end"]), str(r["scope"]), str(r["job"])))
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["period_end", "period", "scope_type", "scope", "job", "salary_wan_month", "source", "source_url"])
        writer.writeheader(); writer.writerows(rows)
    Path(provenance).write_text(json.dumps({
        "notes": [
            "2026Q1 official CALSS regional table is published as an image; CI uses a reviewed transcription and verifies the official image URL is reachable.",
            "A newer 2026Q2 common three-region release has not yet been located; narrower regional/industry Q2 releases are not mixed into this comparable series.",
        ],
        "sources": source_meta,
        "total_rows": len(rows),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(rows)} official recruitment salary rows")


if __name__ == "__main__":
    collect()
