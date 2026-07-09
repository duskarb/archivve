#!/usr/bin/env python3
"""구글 시트(접수함)의 새 항목을 manifest.csv(관리 원본)로 가져온다.

역할 분담:
- 구글 시트 = 접수함. 이름·수업(semester)·링크(original_url)만 넣는 곳.
- manifest.csv = 관리 원본(source of truth). 캡처 결과·상태·메모 등 모든 관리가 여기서 이뤄진다.

sync는 **manifest.csv를 절대 덮어쓰지 않는다.** 시트에만 있는 새 학생을 pending 행으로
'추가'하고, 이미 있는 학생은 빈 칸(링크·제목)만 시트 값으로 채운다(비파괴적).
시트에서 지운 행이 있어도 manifest.csv에서는 지우지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import io
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHEET_ID = "1ttG_2q0ZKYopjJmkPUF9S3d3azgE8ymeFPboMheGVig"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv"

# manifest.csv가 없을 때 새로 만들 기본 컬럼 (편집 칸 왼쪽 / 기계 칸 오른쪽).
DEFAULT_FIELDS = [
    "student_name", "semester", "title", "original_url", "status", "notes",
    "wacz_file", "archived_date", "sha256",
]

# 시트가 접수함으로 채우는 값들. 헤더 이름이 조금 달라도 받아들이도록 별칭을 둔다.
INTAKE_ALIASES = {
    "student_name": ("student_name", "name", "student", "이름", "성명"),
    "semester": ("semester", "class", "course", "수업", "학기"),
    "original_url": ("original_url", "url", "link", "링크", "주소"),
    "title": ("title", "work", "제목", "작품"),
}


def clean(value: str | None) -> str:
    return (value or "").strip()


def slug(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_", "."}:
            allowed.append("-")
    collapsed = "-".join(part for part in "".join(allowed).split("-") if part)
    return collapsed or "untitled"


def row_key(row: dict[str, str]) -> str:
    """학생 식별 키 = 이름+학기. wacz_file 철자가 이름과 달라도 중복이 안 생기게
    항상 이름+학기로 맞춘다. (예전엔 wacz_file을 먼저 써서 철자 차이로 중복이 생겼음)"""
    base = clean(row.get("student_name")) or clean(row.get("title"))
    semester = clean(row.get("semester")) or "undated"
    return f"{slug(base)}-{slug(semester)}"


def read_rows(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text))
    fields = [clean(name) for name in (reader.fieldnames or [])]
    rows = []
    for raw in reader:
        row = {clean(key): clean(value) for key, value in raw.items() if key is not None}
        if any(row.values()):
            rows.append(row)
    return fields, rows


def intake(sheet_row: dict[str, str]) -> dict[str, str]:
    """시트 행에서 접수 필드(이름·수업·링크·제목)만 별칭을 흡수해 뽑아낸다."""
    out = {}
    for canonical, aliases in INTAKE_ALIASES.items():
        for alias in aliases:
            if clean(sheet_row.get(alias)):
                out[canonical] = clean(sheet_row.get(alias))
                break
    return out


def sync(sheet_rows, fields, csv_rows) -> tuple[list, list]:
    by_key = {row_key(row): row for row in csv_rows}
    added, filled = [], []

    for sheet_row in sheet_rows:
        item = intake(sheet_row)
        if not item.get("student_name") and not item.get("original_url"):
            continue

        key = row_key(item)
        if key in by_key:
            # 이미 있는 학생: 관리 데이터는 건드리지 않고, 비어 있는 링크/제목만 채운다.
            row = by_key[key]
            for field in ("original_url", "title"):
                if field in fields and not clean(row.get(field)) and item.get(field):
                    row[field] = item[field]
                    if field == "original_url":
                        filled.append(row)
        else:
            # 새 학생: pending 행으로 추가.
            row = {field: "" for field in fields}
            for field, value in item.items():
                if field in fields:
                    row[field] = value
            if "status" in fields:
                row["status"] = "pending"
            csv_rows.append(row)
            by_key[key] = row
            added.append(row)

    return added, filled


def fetch(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.URLError:
        # macOS의 python.org 배포판은 루트 인증서가 없어 SSL 검증에 실패할 수 있다.
        return subprocess.run(
            ["curl", "-sfL", url],
            capture_output=True, text=True, check=True, timeout=30,
        ).stdout


def write(manifest: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "manifest.csv"))
    parser.add_argument("--sheet-url", default=SHEET_CSV_URL)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    _, sheet_rows = read_rows(fetch(args.sheet_url))
    if not sheet_rows:
        sys.exit("시트를 읽지 못했거나 비어 있습니다. 공유 설정을 확인하세요.")

    manifest = Path(args.manifest)
    if manifest.exists():
        fields, csv_rows = read_rows(manifest.read_text(encoding="utf-8"))
        if not fields:
            fields = list(DEFAULT_FIELDS)
    else:
        fields, csv_rows = list(DEFAULT_FIELDS), []

    added, filled = sync(sheet_rows, fields, csv_rows)
    for row in added:
        print(f"추가: {clean(row.get('student_name')) or row_key(row)} ({clean(row.get('semester'))})")
    for row in filled:
        print(f"링크 채움: {clean(row.get('student_name'))}")
    print(f"시트 {len(sheet_rows)}행 확인 → 새로 {len(added)}명 추가, {len(filled)}명 링크 보완.")

    if args.dry_run:
        writer = csv.DictWriter(sys.stdout, fieldnames=fields)
        writer.writeheader()
        for row in csv_rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        return

    write(manifest, fields, csv_rows)


if __name__ == "__main__":
    main()
