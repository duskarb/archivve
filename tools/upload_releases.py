#!/usr/bin/env python3
"""Upload WACZ files to per-semester GitHub Releases with gh."""

from __future__ import annotations

import argparse
import subprocess
from collections import defaultdict
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def release_exists(tag: str) -> bool:
    result = subprocess.run(["gh", "release", "view", tag], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_list")
    args = parser.parse_args()

    assets_by_semester: dict[str, list[str]] = defaultdict(list)
    asset_list = Path(args.asset_list)
    if not asset_list.exists():
        print("No release asset list found.")
        return

    for line in asset_list.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        semester, path = line.split("\t", 1)
        assets_by_semester[semester or "undated"].append(path)

    for semester, paths in assets_by_semester.items():
        if not release_exists(semester):
            run(["gh", "release", "create", semester, "--title", semester, "--notes", f"Archived websites for {semester}"])
        run(["gh", "release", "upload", semester, *paths, "--clobber"])


if __name__ == "__main__":
    main()
