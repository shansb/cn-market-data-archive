from __future__ import annotations

import csv
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
ASSETS_CSV = ROOT / "reserve-assets" / "assets.csv"
SOURCE_URL = "https://www.safe.gov.cn/safe/2026/0206/27116.html"

FIELDNAMES = [
    "month",
    "item_no",
    "item_cn",
    "item_en",
    "unit",
    "value",
    "source_url",
]


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.table_depth = 0
        self.current_row: list[str] = []
        self.current_cell: list[str] = []
        self.current_colspan = 1
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if not self.in_table:
                self.in_table = True
            self.table_depth += 1
            return
        if not self.in_table:
            return
        if tag == "tr":
            self.in_row = True
            self.current_row = []
            return
        if tag in {"td", "th"} and self.in_row:
            attributes = dict(attrs)
            self.in_cell = True
            self.current_cell = []
            self.current_colspan = int(attributes.get("colspan") or "1")
            return
        if tag == "br" and self.in_cell:
            self.current_cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_table:
            return
        if tag in {"td", "th"} and self.in_cell:
            text = normalize_text("".join(self.current_cell))
            self.current_row.extend([text] * self.current_colspan)
            self.in_cell = False
            return
        if tag == "tr" and self.in_row:
            self.rows.append(self.current_row)
            self.in_row = False
            return
        if tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current_cell.append(data)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def current_date() -> datetime:
    override = os.environ.get("RUN_DATE")
    if override:
        return datetime.strptime(override, "%Y%m%d")
    return datetime.now()


def should_run(now: datetime) -> bool:
    return os.environ.get("FORCE_RUN") == "1" or (
        now.year == 2026 and now.day == 10
    )


def fetch_html() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    with urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def split_item(text: str) -> tuple[str, str, str]:
    match = re.match(r"^(?:(\d+)\.\s*)?(.+?)\s{1,}([A-Za-z].*)$", text)
    if not match:
        raise ValueError(f"Cannot parse item cell: {text}")
    return match.group(1) or "", match.group(2).strip(), match.group(3).strip()


def parse_value(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    number_match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return number_match.group(0) if number_match else text


def unit_for_column(column_index: int) -> str:
    return "100million USD" if column_index % 2 == 1 else "100million SDR"


def parse_assets(html: str) -> list[dict[str, str]]:
    parser = TableParser()
    parser.feed(html)
    rows = parser.rows

    month_row = next((row for row in rows if row and "项目 Item" in row[0]), None)
    if not month_row:
        raise ValueError("Cannot find month header row")

    records: list[dict[str, str]] = []
    for row in rows:
        if not row:
            continue
        item = row[0]
        if not item or item in {"项目 Item", "官方储备资产 Official reserve assets"}:
            continue
        if "Foreign currency reserves" in item or "IMF reserve position" in item:
            item_no, item_cn, item_en = split_item(item)
        elif "SDRs" in item and "特别提款权" in item:
            item_no, item_cn, item_en = split_item(item)
        elif "Gold" in item and "黄金" in item:
            item_no, item_cn, item_en = split_item(item)
        elif "Other reserve assets" in item:
            item_no, item_cn, item_en = split_item(item)
        elif "Total" in item and "合计" in item:
            item_no, item_cn, item_en = "", "合计", "Total"
        else:
            continue

        for column_index, cell in enumerate(row[1:], start=1):
            value = parse_value(cell)
            if not value:
                continue
            month = month_row[column_index] if column_index < len(month_row) else ""
            if not re.fullmatch(r"2026\.\d{2}", month):
                continue
            records.append(
                {
                    "month": month.replace(".", "-"),
                    "item_no": item_no,
                    "item_cn": item_cn,
                    "item_en": item_en,
                    "unit": unit_for_column(column_index),
                    "value": value,
                    "source_url": SOURCE_URL,
                }
            )

    records.extend(parse_gold_ounces(rows, month_row))
    if not records:
        raise ValueError("No official reserve asset records parsed")
    return records


def parse_gold_ounces(
    rows: list[list[str]], month_row: list[str]
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in rows:
        if not row or row[0] or not any("万盎司" in cell for cell in row):
            continue
        for column_index, cell in enumerate(row[1:], start=1):
            if column_index % 2 == 0:
                continue
            if "万盎司" not in cell:
                continue
            month = month_row[column_index] if column_index < len(month_row) else ""
            if not re.fullmatch(r"2026\.\d{2}", month):
                continue
            records.append(
                {
                    "month": month.replace(".", "-"),
                    "item_no": "4",
                    "item_cn": "黄金储备数量",
                    "item_en": "Gold reserves volume",
                    "unit": "10000 fine troy ounces",
                    "value": parse_value(cell),
                    "source_url": SOURCE_URL,
                }
            )
    return records


def write_assets(records: list[dict[str, str]]) -> None:
    ASSETS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with ASSETS_CSV.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def main() -> int:
    now = current_date()
    if not should_run(now):
        print(f"{now:%Y%m%d}: not a scheduled 2026 monthly run date; skipping.")
        return 0

    records = parse_assets(fetch_html())
    write_assets(records)
    print(f"Updated {ASSETS_CSV.relative_to(ROOT)} with {len(records)} records.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
