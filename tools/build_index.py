#!/usr/bin/env python3
"""Build site/index.json from manifest.csv."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.csv"
OUT = ROOT / "site" / "index.json"


def clean(value: str | None) -> str:
    return (value or "").strip()


def computed_wacz_url(row: dict[str, str]) -> str:
    wacz_file = clean(row.get("wacz_file"))
    semester = clean(row.get("semester"))
    public_wacz_base = os.environ.get("ARCHIVE_PUBLIC_WACZ_BASE", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    release_base = os.environ.get("ARCHIVE_RELEASE_BASE", "")

    if public_wacz_base and semester and wacz_file:
        return f"{public_wacz_base.rstrip('/')}/{semester}/{wacz_file}"

    explicit = clean(row.get("wacz_url"))
    if explicit:
        return explicit

    if not release_base and repository:
        release_base = f"https://github.com/{repository}/releases/download"

    if release_base and semester and wacz_file:
        return f"{release_base.rstrip('/')}/{semester}/{wacz_file}"

    return ""


def main() -> None:
    rows = []
    if MANIFEST.exists():
        with MANIFEST.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if not any(clean(value) for value in row.values()):
                    continue
                normalized = {key: clean(value) for key, value in row.items()}
                # 학생 요청/저작권/개인정보 비공개 항목은 공개 색인에 싣지 않는다.
                if normalized.get("status", "").lower() in {"private", "hidden"}:
                    continue
                normalized["wacz_url"] = computed_wacz_url(normalized)
                rows.append(normalized)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
