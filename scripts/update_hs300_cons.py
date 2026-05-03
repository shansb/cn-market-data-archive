from __future__ import annotations

import csv
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
HOLIDAY_CSV = ROOT / "法定节假日.csv"
SOURCE_CODE_COLUMN = "成份券代码Constituent Code"
INDEXES = [
    {
        "name": "沪深300",
        "download_prefix": "000300cons",
        "target_dir": ROOT / "00300-沪深300",
        "source_url": (
            "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
            "file/autofile/cons/000300cons.xls"
        ),
    },
    {
        "name": "科创50",
        "download_prefix": "000688cons",
        "target_dir": ROOT / "000688-科创50",
        "source_url": (
            "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/"
            "file/autofile/cons/000688cons.xls"
        ),
    },
]


def current_yyyymmdd() -> str:
    override = os.environ.get("RUN_DATE")
    if override:
        return datetime.strptime(override, "%Y%m%d").strftime("%Y%m%d")
    return datetime.now().strftime("%Y%m%d")


def load_holidays() -> set[str]:
    with HOLIDAY_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if "date" not in (reader.fieldnames or []):
            raise ValueError(f"{HOLIDAY_CSV} must contain a 'date' column")
        return {row["date"].strip() for row in reader if row.get("date")}


def read_current_codes(cons_csv: Path) -> list[str]:
    with cons_csv.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if "code" not in (reader.fieldnames or []):
            raise ValueError(f"{cons_csv} must contain a 'code' column")
        return [normalize_code(row["code"]) for row in reader if row.get("code")]


def normalize_code(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.isdigit():
        return text.zfill(6)
    return text


def download_source(source_url: str, download_prefix: str) -> Path:
    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        },
    )
    fd, name = tempfile.mkstemp(prefix=f"{download_prefix}-", suffix=".xls")
    os.close(fd)
    path = Path(name)
    with urlopen(request, timeout=60) as response, path.open("wb") as file:
        shutil.copyfileobj(response, file)
    return path


def read_source_codes(path: Path) -> list[str]:
    frame = pd.read_excel(path, dtype=str)
    if SOURCE_CODE_COLUMN not in frame.columns:
        raise ValueError(
            f"Downloaded file does not contain column: {SOURCE_CODE_COLUMN}. "
            f"Columns: {', '.join(map(str, frame.columns))}"
        )
    codes = [normalize_code(value) for value in frame[SOURCE_CODE_COLUMN].tolist()]
    return [code for code in codes if code]


def write_codes(cons_csv: Path, codes: list[str]) -> None:
    with cons_csv.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["code"])
        writer.writerows([code] for code in codes)


def update_index(config: dict[str, object], today: str) -> None:
    target_dir = config["target_dir"]
    if not isinstance(target_dir, Path):
        raise TypeError("target_dir must be a Path")
    cons_csv = target_dir / "cons.csv"
    archive_dir = target_dir / "archive"

    downloaded = download_source(
        str(config["source_url"]),
        str(config["download_prefix"]),
    )
    try:
        source_codes = read_source_codes(downloaded)
        current_codes = read_current_codes(cons_csv)
        if source_codes == current_codes:
            print(f"{today}: {config['name']} constituent codes unchanged.")
            return

        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"{today}.xlsx"
        shutil.move(str(downloaded), archive_path)
        write_codes(cons_csv, source_codes)
        print(
            f"{today}: updated {cons_csv.relative_to(ROOT)} with "
            f"{len(source_codes)} codes and archived {archive_path.relative_to(ROOT)}."
        )
    finally:
        if downloaded.exists():
            downloaded.unlink()


def main() -> int:
    today = current_yyyymmdd()
    if today in load_holidays():
        print(f"{today} is in {HOLIDAY_CSV.name}; skipping.")
        return 0

    for config in INDEXES:
        update_index(config, today)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
