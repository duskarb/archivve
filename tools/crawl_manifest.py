#!/usr/bin/env python3
"""Capture selected manifest rows with Playwright (no Docker)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
# 편집 칸(왼쪽) + 기계가 채우는 칸(오른쪽). type·wacz_url은 쓰지 않는다.
DEFAULT_FIELDS = [
    "student_name",
    "semester",
    "title",
    "original_url",
    "status",
    "notes",
    "drive_link",
    "wacz_file",
    "archived_date",
    "sha256",
]


def clean(value: str | None) -> str:
    return (value or "").strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def slug(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_", "."}:
            allowed.append("-")
    collapsed = "-".join(part for part in "".join(allowed).split("-") if part)
    return collapsed or "untitled"


def read_manifest(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or DEFAULT_FIELDS)
        rows = [{key: clean(value) for key, value in row.items()} for row in reader]

    for field in DEFAULT_FIELDS:
        if field not in fields:
            fields.append(field)

    return fields, rows


def write_manifest(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def row_matches(row: dict[str, str], match: str) -> bool:
    if not match:
        return True

    needle = match.lower()
    haystack = " ".join(
        clean(row.get(field))
        for field in ("student_name", "title", "original_url", "semester", "notes")
    ).lower()
    return needle in haystack


def should_capture(row: dict[str, str], semester: str, mode: str, match: str) -> bool:
    status = clean(row.get("status")).lower()
    if not clean(row.get("original_url")):
        return False
    if status in {"private", "hidden"}:
        return False
    if semester and clean(row.get("semester")) != semester:
        return False
    if not row_matches(row, match):
        return False
    if mode == "all":
        return True
    return status in {"", "pending", "ready-to-capture", "recapture-needed"}


def run_crawl(args: argparse.Namespace, row: dict[str, str], out_dir: Path) -> Path:
    """Docker 없이 Playwright로 캡처해 out_dir/<semester>/<wacz_file> 에 저장한다."""
    from capture_playwright import capture

    semester = clean(row.get("semester")) or "undated"
    base_id = clean(row.get("student_name")) or clean(row.get("title"))
    wacz_file = clean(row.get("wacz_file")) or f"{slug(base_id)}-{slug(semester)}.wacz"
    target = out_dir / semester / wacz_file
    target.parent.mkdir(parents=True, exist_ok=True)

    capture(
        clean(row.get("original_url")),
        target,
        page_limit=int(args.page_limit),
        depth=int(args.depth),
        title=clean(row.get("title")) or wacz_file.removesuffix(".wacz"),
        description=f"{clean(row.get('student_name'))} / {semester}",
    )

    row["wacz_file"] = wacz_file
    row["archived_date"] = datetime.now(timezone.utc).date().isoformat()
    row["sha256"] = sha256(target)
    # 캡처 성공과 재생 성공은 다르다. 운영자가 ReplayWeb.page에서 확인한 뒤
    # ok 또는 partial로 올린다.
    row["status"] = "review-needed"
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "manifest.csv"))
    parser.add_argument("--out-dir", default=str(ROOT / "wacz"))
    parser.add_argument("--semester", default="")
    parser.add_argument("--mode", choices=["pending", "all"], default="pending")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--page-limit", type=int, default=30)
    parser.add_argument("--match", default="")
    args = parser.parse_args()

    manifest = Path(args.manifest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields, rows = read_manifest(manifest)
    selected = [row for row in rows if should_capture(row, args.semester, args.mode, args.match)]
    failed: list[str] = []

    for row in selected:
        url = clean(row.get("original_url"))
        print(f"캡처 중: {clean(row.get('student_name')) or url} — {url}")
        try:
            run_crawl(args, row, out_dir)
        except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError) as error:
            print(f"ERROR: {url} failed: {error}")
            row["status"] = "recapture-needed"
            failed.append(url)
            continue

    write_manifest(manifest, fields, rows)
    print(f"Captured {len(selected) - len(failed)} of {len(selected)} item(s).")
    if failed:
        print("Some crawls failed; successful WACZ files will still be uploaded:")
        for url in failed:
            print(f"  - {url}")


if __name__ == "__main__":
    main()
