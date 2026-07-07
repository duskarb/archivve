#!/usr/bin/env python3
"""Docker 없이 사이트를 캡처해 WACZ로 저장한다.

실제 Chromium(Playwright)을 띄워 페이지를 로드하고, 오가는 모든 응답을
WARC로 기록한 뒤 wacz 패키지로 WACZ를 만든다. browsertrix와 같은 방식(실제
브라우저 렌더링)이라 자바스크립트가 있는 사이트도 재생 품질이 좋다.

같은 prefix(같은 사이트) 내부 링크를 depth/page-limit 범위에서 따라간다.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urldefrag, urlsplit

from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

# 재생 시 문제를 일으키는 헤더는 걷어낸다.
# (Playwright의 body()는 압축이 풀린 바이트를 주므로 content-encoding/length를 버린다.)
_SKIP_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "connection"}

# 스크롤로 지연 로딩 콘텐츠를 끌어낸 뒤 맨 위로 돌아온다.
_AUTOSCROLL = """
async () => {
  const step = () => new Promise(r => setTimeout(r, 250));
  let last = -1;
  for (let i = 0; i < 40; i++) {
    window.scrollTo(0, document.body.scrollHeight);
    await step();
    const h = document.body.scrollHeight;
    if (h === last) break;
    last = h;
  }
  window.scrollTo(0, 0);
}
"""


def _scope_prefix(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rsplit("/", 1)[0] + "/" if "/" in parts.path else "/"
    return f"{parts.scheme}://{parts.netloc}{path}"


def _in_scope(url: str, prefix: str) -> bool:
    return url.startswith(prefix)


def _write_record(writer: WARCWriter, response, body: bytes) -> None:
    raw = response.request
    url = response.url

    headers = [(k, v) for k, v in response.headers.items() if k.lower() not in _SKIP_HEADERS]
    headers.append(("Content-Length", str(len(body))))
    status_line = f"{response.status} {response.status_text or 'OK'}"
    http_headers = StatusAndHeaders(status_line, headers, protocol="HTTP/1.1")
    record = writer.create_warc_record(
        url, "response", payload=BytesIO(body), http_headers=http_headers
    )
    writer.write_record(record)

    req_headers = StatusAndHeaders(
        f"{raw.method} {urlsplit(url).path or '/'} HTTP/1.1",
        [(k, v) for k, v in raw.headers.items() if k.lower() not in _SKIP_HEADERS],
        is_http_request=True,
    )
    writer.write_record(
        writer.create_warc_record(url, "request", http_headers=req_headers)
    )


def _capture_to_warc(seed_url: str, warc_path: Path, page_limit: int, depth: int):
    from playwright.sync_api import sync_playwright

    prefix = _scope_prefix(seed_url)
    seen_resources: set[str] = set()
    visited_pages: set[str] = set()
    pages: list[dict] = []
    queue: list[tuple[str, int]] = [(urldefrag(seed_url).url, 0)]
    written = 0

    with open(warc_path, "wb") as stream:
        writer = WARCWriter(stream, gzip=True)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36 archivve-playwright"
                )
            )
            page = context.new_page()
            pending = []
            page.on("response", lambda response: pending.append(response))

            while queue and len(visited_pages) < page_limit:
                url, level = queue.pop(0)
                if url in visited_pages:
                    continue
                visited_pages.add(url)
                pending.clear()

                page_title = url
                try:
                    page.goto(url, wait_until="load", timeout=45000)
                    page.wait_for_timeout(1200)
                    page.evaluate(_AUTOSCROLL)
                    page.wait_for_timeout(500)
                    page_title = page.title() or url
                except Exception as error:  # noqa: BLE001
                    print(f"    warn: {url} 로드 경고: {error}")

                pages.append({
                    "id": hashlib.sha1(url.encode()).hexdigest()[:16],
                    "url": url,
                    "title": page_title,
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

                for response in list(pending):
                    res_url = urldefrag(response.url).url
                    if not res_url.startswith(("http://", "https://")):
                        continue
                    if res_url in seen_resources:
                        continue
                    seen_resources.add(res_url)
                    try:
                        body = response.body()
                    except Exception:  # noqa: BLE001 (리다이렉트 등 본문 없음)
                        body = b""
                    try:
                        _write_record(writer, response, body)
                        written += 1
                    except Exception as error:  # noqa: BLE001
                        print(f"    warn: {res_url} 기록 실패: {error}")

                if level < depth:
                    try:
                        links = page.eval_on_selector_all(
                            "a[href]", "els => els.map(e => e.href)"
                        )
                    except Exception:  # noqa: BLE001
                        links = []
                    for link in links:
                        target = urldefrag(link).url
                        if _in_scope(target, prefix) and target not in visited_pages:
                            queue.append((target, level + 1))

            browser.close()

    return written, pages


def _wacz_bin() -> str:
    candidate = Path(sys.executable).parent / "wacz"
    return str(candidate) if candidate.exists() else "wacz"


def capture(seed_url: str, wacz_path: Path, page_limit: int = 30, depth: int = 3,
            title: str = "", description: str = "") -> Path:
    """seed_url을 캡처해 wacz_path에 WACZ를 만든다. 만들어진 경로를 반환."""
    wacz_path = Path(wacz_path)
    wacz_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        warc_path = Path(tmp) / "capture.warc.gz"
        count, pages = _capture_to_warc(seed_url, warc_path, page_limit, depth)
        if count == 0:
            raise RuntimeError(f"{seed_url} 에서 기록된 응답이 없습니다.")
        print(f"    {count}개 리소스, {len(pages)}개 페이지 기록 → WACZ 패키징")

        pages_path = Path(tmp) / "pages.jsonl"
        with pages_path.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(
                {"format": "json-pages-1.0", "id": "pages", "title": "All Pages"}
            ) + "\n")
            for entry in pages:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

        argv = [
            _wacz_bin(), "create", str(warc_path),
            "-o", str(wacz_path),
            "--pages", str(pages_path), "--url", seed_url,
        ]
        if title:
            argv += ["--title", title]
        if description:
            argv += ["--desc", description]
        subprocess.run(argv, check=True, env={**os.environ})

    return wacz_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Docker 없이 사이트를 WACZ로 캡처")
    parser.add_argument("url")
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--page-limit", type=int, default=30)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--title", default="")
    parser.add_argument("--description", default="")
    args = parser.parse_args()

    out = capture(
        args.url, Path(args.out), args.page_limit, args.depth,
        args.title, args.description,
    )
    print(f"저장됨: {out}")
