#!/usr/bin/env python3
"""Capture selected manifest rows with Browsertrix Crawler."""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIELDS = [
    "student_name",
    "title",
    "original_url",
    "semester",
    "wacz_file",
    "wacz_url",
    "archived_date",
    "sha256",
    "status",
    "notes",
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
    if status == "private":
        return False
    if semester and clean(row.get("semester")) != semester:
        return False
    if not row_matches(row, match):
        return False
    if mode == "all":
        return True
    return status in {"", "pending", "recapture-needed"}


def find_wacz(crawls_dir: Path, collection: str) -> Path:
    expected = crawls_dir / "collections" / collection / f"{collection}.wacz"
    if expected.exists():
        return expected

    matches = list(crawls_dir.rglob(f"{collection}.wacz"))
    if matches:
        return matches[0]

    raise FileNotFoundError(f"Could not find {collection}.wacz under {crawls_dir}")


def run_crawl(args: argparse.Namespace, row: dict[str, str], out_dir: Path) -> Path:
    semester = clean(row.get("semester")) or "undated"
    base_id = clean(row.get("student_name")) or clean(row.get("title"))
    wacz_file = clean(row.get("wacz_file")) or f"{slug(base_id)}-{slug(semester)}.wacz"
    collection = wacz_file.removesuffix(".wacz")
    crawls_dir = ROOT / "crawls"

    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{crawls_dir}:/crawls/",
        args.image,
        "crawl",
        "--url",
        clean(row.get("original_url")),
        "--scopeType",
        args.scope_type,
        "--depth",
        str(args.depth),
        "--pageLimit",
        str(args.page_limit),
        "--behaviors",
        args.behaviors,
        "--generateWACZ",
        "--collection",
        collection,
        "--overwrite",
        "--title",
        clean(row.get("title")) or collection,
        "--description",
        f"{clean(row.get('student_name'))} / {semester}",
    ]

    subprocess.run(command, cwd=ROOT, check=True)
    found = find_wacz(crawls_dir, collection)
    target = out_dir / semester / wacz_file
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(found, target)

    row["wacz_file"] = wacz_file
    row["archived_date"] = datetime.now(timezone.utc).date().isoformat()
    row["sha256"] = sha256(target)
    # 캡처 성공과 재생 성공은 다르다: 운영자가 재생을 확인한 뒤 직접 ok로 바꾼다.
    row["status"] = "review-needed"
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "manifest.csv"))
    parser.add_argument("--out-dir", default=str(ROOT / "out"))
    parser.add_argument("--semester", default="")
    parser.add_argument("--mode", choices=["pending", "all"], default="pending")
    parser.add_argument("--image", default="webrecorder/browsertrix-crawler:1.13.0")
    parser.add_argument("--scope-type", default="prefix")
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument("--page-limit", type=int, default=100)
    parser.add_argument("--behaviors", default="autoscroll")
    parser.add_argument("--match", default="")
    args = parser.parse_args()

    manifest = Path(args.manifest)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fields, rows = read_manifest(manifest)
    selected = [row for row in rows if should_capture(row, args.semester, args.mode, args.match)]
    asset_list = out_dir / "release-assets.tsv"
    failed: list[str] = []

    with asset_list.open("w", encoding="utf-8") as assets:
        for row in selected:
            url = clean(row.get("original_url"))
            try:
                target = run_crawl(args, row, out_dir)
            except (subprocess.CalledProcessError, FileNotFoundError) as error:
                print(f"ERROR: {url} failed: {error}")
                row["status"] = "recapture-needed"
                failed.append(url)
                continue
            assets.write(f"{clean(row.get('semester'))}\t{target}\n")

    write_manifest(manifest, fields, rows)
    print(f"Captured {len(selected) - len(failed)} of {len(selected)} item(s).")
    if failed:
        print("Some crawls failed; successful WACZ files will still be uploaded:")
        for url in failed:
            print(f"  - {url}")


if __name__ == "__main__":
    main()
