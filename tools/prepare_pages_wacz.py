#!/usr/bin/env python3
"""Mirror WACZ files into site/wacz for same-origin Pages playback."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def clean(value: str | None) -> str:
    return (value or "").strip()


def release_url(row: dict[str, str]) -> str:
    explicit = clean(row.get("wacz_url"))
    if explicit:
        return explicit

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    semester = clean(row.get("semester"))
    wacz_file = clean(row.get("wacz_file"))
    if repository and semester and wacz_file:
        return f"https://github.com/{repository}/releases/download/{semester}/{wacz_file}"

    return ""


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "class-web-archive"})
    tmp = target.with_suffix(target.suffix + ".tmp")
    with urllib.request.urlopen(request, timeout=120) as response, tmp.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    tmp.replace(target)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(ROOT / "manifest.csv"))
    parser.add_argument("--out-dir", default=str(ROOT / "out"))
    parser.add_argument("--site-dir", default=str(ROOT / "site"))
    args = parser.parse_args()

    manifest = Path(args.manifest)
    out_dir = Path(args.out_dir)
    target_root = Path(args.site_dir) / "wacz"

    if target_root.exists():
        shutil.rmtree(target_root)
    target_root.mkdir(parents=True, exist_ok=True)

    missing: list[str] = []
    mirrored: set[tuple[str, str]] = set()
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if clean(row.get("status")).lower() == "private":
                continue

            semester = clean(row.get("semester"))
            wacz_file = clean(row.get("wacz_file"))
            if not semester or not wacz_file:
                continue

            key = (semester, wacz_file)
            if key in mirrored:
                continue
            mirrored.add(key)

            target = target_root / semester / wacz_file
            target.parent.mkdir(parents=True, exist_ok=True)

            local = out_dir / semester / wacz_file
            if local.exists():
                shutil.copy2(local, target)
                continue

            url = release_url(row)
            if not url:
                missing.append(f"{semester}/{wacz_file}: no release URL")
                continue

            try:
                download(url, target)
            except Exception as error:  # noqa: BLE001 - report every failed asset.
                missing.append(f"{semester}/{wacz_file}: {error}")

    print(f"Prepared {len(mirrored) - len(missing)} WACZ file(s) for Pages playback.")
    if missing:
        print("Missing WACZ file(s):", file=sys.stderr)
        for item in missing:
            print(f"  - {item}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
