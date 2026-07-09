#!/usr/bin/env python3
"""Validate manifest.csv status values and required fields."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_STATUSES = {
    "",
    "pending",
    "ready-to-capture",
    "review-needed",
    "ok",
    "partial",
    "recapture-needed",
    "private",
    "hidden",
}
URL_REQUIRED_STATUSES = {
    "ready-to-capture",
    "review-needed",
    "ok",
    "partial",
    "recapture-needed",
}
WACZ_EXPECTED_STATUSES = {"review-needed", "ok", "partial"}


def clean(value: str | None) -> str:
    return (value or "").strip()


def valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", nargs="?", default=str(ROOT / "manifest.csv"))
    args = parser.parse_args()

    path = Path(args.manifest)
    errors: list[str] = []
    warnings: list[str] = []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"student_name", "original_url", "semester", "status"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            errors.append(f"missing column(s): {', '.join(missing)}")

        seen_names: dict[tuple[str, str], int] = {}
        for number, row in enumerate(reader, start=2):
            name = clean(row.get("student_name"))
            title = clean(row.get("title"))
            semester = clean(row.get("semester"))
            status = clean(row.get("status")).lower()
            url = clean(row.get("original_url"))
            wacz = clean(row.get("wacz_file")) or clean(row.get("wacz_url"))

            label = f"line {number} ({name or title or 'untitled'})"
            if not name:
                errors.append(f"{label}: student_name is empty")
            if not semester:
                errors.append(f"{label}: semester is empty")
            if status not in ALLOWED_STATUSES:
                errors.append(f"{label}: unknown status '{status}'")
            if status in URL_REQUIRED_STATUSES and not url:
                errors.append(f"{label}: original_url is required for status '{status}'")
            if url and not valid_url(url):
                errors.append(f"{label}: original_url must start with http:// or https://")
            if status in WACZ_EXPECTED_STATUSES and not wacz:
                warnings.append(f"{label}: wacz_file or wacz_url is expected for status '{status}'")
            if not status:
                warnings.append(f"{label}: blank status is treated as pending")

            key = (semester, name.lower())
            if semester and name:
                if key in seen_names:
                    warnings.append(f"{label}: duplicate student_name in {semester}; first seen on line {seen_names[key]}")
                else:
                    seen_names[key] = number

    for item in warnings:
        print(f"WARNING: {item}", file=sys.stderr)
    for item in errors:
        print(f"ERROR: {item}", file=sys.stderr)

    if errors:
        raise SystemExit(1)

    print(f"Validated {path}")


if __name__ == "__main__":
    main()
