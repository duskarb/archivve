#!/usr/bin/env python3
"""Cross-platform command runner for archivve."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPTURE_DEPS = {
    "playwright": "playwright",
    "warcio": "warcio",
    "wacz": "wacz",
    "PIL": "pillow",
}


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, check=check)


def missing_capture_deps() -> list[str]:
    missing = []
    for module, package in CAPTURE_DEPS.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)
    return missing


def install_capture_deps() -> None:
    run([sys.executable, "-m", "pip", "install", "--upgrade", "playwright", "warcio", "wacz", "pillow"])
    run([sys.executable, "-m", "playwright", "install", "chromium"])


def prompt_install(missing: list[str]) -> bool:
    print("Capture dependencies are missing:", ", ".join(missing))
    print("Install command:")
    print(f"  {sys.executable} -m pip install playwright warcio wacz pillow")
    print(f"  {sys.executable} -m playwright install chromium")
    if not sys.stdin.isatty():
        return False
    answer = input("Install now? [y/N] ").strip().lower()
    return answer in {"y", "yes"}


def sync_manifest() -> None:
    result = run([sys.executable, "tools/sync_manifest.py"], check=False)
    if result.returncode != 0:
        print("Could not read the Google Sheet; continuing with the local manifest.csv.")


def capture_targets() -> list[str]:
    manifest = ROOT / "manifest.csv"
    if not manifest.exists():
        return []

    targets = []
    with manifest.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            status = (row.get("status") or "").strip().lower()
            url = (row.get("original_url") or "").strip()
            if url and status in {"", "pending", "ready-to-capture", "recapture-needed"}:
                targets.append((row.get("student_name") or row.get("title") or "Untitled").strip())
    return targets


def capture(args: argparse.Namespace) -> int:
    missing = missing_capture_deps()
    if missing:
        if args.install or prompt_install(missing):
            install_capture_deps()
        else:
            return 1

    print("1) Syncing new rows from the Google Sheet...")
    sync_manifest()

    targets = capture_targets()
    if not targets:
        print("No rows need capture.")
        return 0

    print(f"2) {len(targets)} row(s) need capture:")
    for name in targets:
        print(f"   - {name}")

    if not args.yes and sys.stdin.isatty():
        answer = input("Press Enter to capture, or type n then Enter to cancel: ").strip().lower()
        if answer.startswith("n"):
            print("Cancelled.")
            return 0

    command = [
        sys.executable,
        "tools/crawl_manifest.py",
        "--mode",
        "pending",
        "--out-dir",
        "wacz",
        "--page-limit",
        str(args.page_limit),
        "--depth",
        str(args.depth),
    ]
    print("3) Capturing...")
    run(command)
    print("Done. Run `python3 archive.py view` to review the archive.")
    return 0


def port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_later(url: str) -> None:
    time.sleep(0.8)
    webbrowser.open(url)


def view(args: argparse.Namespace) -> int:
    path = "index.html?mode=all" if args.all else "index.html"
    url = f"http://localhost:{args.port}/{path}"

    if port_is_open(args.port):
        print(f"Using an existing server at {url}")
        webbrowser.open(url)
        return 0

    print(f"Serving {ROOT} at {url}")
    print("Keep this terminal open while viewing the archive.")
    threading.Thread(target=open_later, args=(url,), daemon=True).start()
    return run([sys.executable, "tools/serve.py", str(args.port), str(ROOT)], check=False).returncode


def edit(_: argparse.Namespace) -> int:
    editor = ROOT / "tools" / "manifest-editor.html"
    webbrowser.open(editor.resolve().as_uri())
    print(f"Opened {editor}")
    return 0


def doctor(_: argparse.Namespace) -> int:
    print(f"Python: {sys.executable}")
    print(f"Project: {ROOT}")
    missing = missing_capture_deps()
    if missing:
        print("Missing capture dependencies:", ", ".join(missing))
        return 1
    print("Capture dependencies: ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run archivve without OS-specific wrapper scripts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture_parser = subparsers.add_parser("capture", help="sync the sheet and capture pending rows")
    capture_parser.add_argument("--install", action="store_true", help="install missing capture dependencies")
    capture_parser.add_argument("-y", "--yes", action="store_true", help="capture without prompting")
    capture_parser.add_argument("--page-limit", type=int, default=30)
    capture_parser.add_argument("--depth", type=int, default=3)
    capture_parser.set_defaults(func=capture)

    view_parser = subparsers.add_parser("view", help="serve the archive locally and open the browser")
    view_parser.add_argument("--all", action="store_true", help="open the management/all rows mode")
    view_parser.add_argument("--port", type=int, default=8817)
    view_parser.set_defaults(func=view)

    edit_parser = subparsers.add_parser("edit", help="open the local manifest CSV editor")
    edit_parser.set_defaults(func=edit)

    doctor_parser = subparsers.add_parser("doctor", help="check local capture dependencies")
    doctor_parser.set_defaults(func=doctor)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
