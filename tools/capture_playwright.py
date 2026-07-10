#!/usr/bin/env python3
"""Docker 없이 사이트를 캡처해 WACZ로 저장한다.

실제 Chromium(Playwright)을 띄워 페이지를 로드하고, 오가는 모든 응답을
WARC로 기록한 뒤 wacz 패키지로 WACZ를 만든다. browsertrix와 같은 방식(실제
브라우저 렌더링)이라 자바스크립트가 있는 사이트도 재생 품질이 좋다.

같은 prefix(같은 사이트) 내부 링크를 depth/page-limit 범위에서 따라간다.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

from warcio.statusandheaders import StatusAndHeaders
from warcio.warcwriter import WARCWriter

# 재생 시 문제를 일으키는 헤더는 걷어낸다.
# (Playwright의 body()는 압축이 풀린 바이트를 주므로 content-encoding/length를 버린다.)
_SKIP_HEADERS = {"content-encoding", "content-length", "transfer-encoding", "connection"}

# ── 이미지 최적화 설정 (환경변수로 조절 가능, ARCHIVE_OPTIMIZE=0 이면 끔) ──
# 학생들이 최적화 안 한 큰 사진을 그대로 올리면 WACZ가 커진다. 캡처 시 큰 이미지를
# 화면 크기 수준으로 다운스케일하고 재압축해 용량을 줄인다(원본보다 작을 때만 교체).
_OPTIMIZE = os.environ.get("ARCHIVE_OPTIMIZE", "1") != "0"
_OPT_MAX_DIM = int(os.environ.get("ARCHIVE_IMG_MAX_DIM", "2000"))   # 긴 변 최대 px
_OPT_QUALITY = int(os.environ.get("ARCHIVE_IMG_QUALITY", "82"))     # JPEG 품질
_OPT_MIN_BYTES = int(os.environ.get("ARCHIVE_IMG_MIN_BYTES", "300000"))  # 이 이하는 손대지 않음


def _optimize_image(content_type: str, body: bytes) -> tuple[bytes, str]:
    """큰 이미지를 다운스케일·재압축한다. 원본보다 작아질 때만 교체.
    반환: (새 body, 새 content_type). Pillow가 없거나 처리 불가면 원본 그대로."""
    if not _OPTIMIZE or len(body) < _OPT_MIN_BYTES:
        return body, content_type
    ct = (content_type or "").lower()
    if "image/jpeg" not in ct and "image/png" not in ct:
        return body, content_type
    try:
        from PIL import Image
    except Exception:
        return body, content_type
    try:
        im = Image.open(BytesIO(body))
        im.load()
    except Exception:
        return body, content_type
    if getattr(im, "is_animated", False):  # 애니메이션(APNG 등)은 건드리지 않는다
        return body, content_type

    width, height = im.size
    if max(width, height) > _OPT_MAX_DIM:
        scale = _OPT_MAX_DIM / max(width, height)
        im = im.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.LANCZOS)

    has_alpha = "a" in im.mode.lower() or (im.mode == "P" and "transparency" in im.info)
    out = BytesIO()
    if "png" in ct and has_alpha:
        # 투명도가 있으면 PNG 유지(투명 손실 방지), 크기만 최적화.
        im.save(out, format="PNG", optimize=True)
        new_ct = "image/png"
    else:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.save(out, format="JPEG", quality=_OPT_QUALITY, optimize=True, progressive=True)
        new_ct = "image/jpeg"

    data = out.getvalue()
    return (data, new_ct) if len(data) < len(body) else (body, content_type)

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

# JavaScript가 클릭 뒤에만 img.src를 지정하는 경우에도 파일을 안전하게 로드한다.
# 버튼 자체를 누르지 않으므로 폼 제출이나 기타 라이브 사이트 부작용은 만들지 않는다.
_PRELOAD_IMAGES = """
async (urls) => {
  await Promise.all(urls.map(url => new Promise(resolve => {
    const image = new Image();
    const done = () => resolve();
    image.onload = done;
    image.onerror = done;
    image.src = url;
    setTimeout(done, 10000);
  })));
}
"""


_SCRIPT_NAVIGATION_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    # Inline click handlers and scripts that replace the current page.
    r"(?:window\s*\.\s*)?(?:document\s*\.\s*)?location(?:\s*\.\s*href)?\s*=\s*"
    r"(?P<quote>['\"`])(?P<url>.+?)(?P=quote)",
    r"(?:window\s*\.\s*)?(?:document\s*\.\s*)?location\s*\.\s*"
    r"(?:assign|replace)\s*\(\s*(?P<quote>['\"`])(?P<url>.+?)(?P=quote)",
    # New-window navigation is still replayable when its destination is archived.
    r"window\s*\.\s*open\s*\(\s*(?P<quote>['\"`])(?P<url>.+?)(?P=quote)",
    # Common History API and SPA router forms.
    r"history\s*\.\s*(?:pushState|replaceState)\s*\(\s*[^,]*,\s*[^,]*,\s*"
    r"(?P<quote>['\"`])(?P<url>.+?)(?P=quote)",
    r"(?:router\s*\.\s*(?:push|replace)|navigate)\s*\(\s*"
    r"(?P<quote>['\"`])(?P<url>.+?)(?P=quote)",
))

_STATIC_IMAGE_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    # Literal paths in JS data, such as { image: "images/stone2.jpg" }.
    r"(?P<quote>['\"`])(?P<url>[^'\"`\r\n]+?\."
    r"(?:avif|gif|jpe?g|png|svg|webp)(?:\?[^'\"`\r\n]*)?)(?P=quote)",
    # CSS background images in inline/external styles.
    r"url\(\s*(?P<quote>['\"]?)(?P<url>[^)'\"\r\n]+?\."
    r"(?:avif|gif|jpe?g|png|svg|webp)(?:\?[^)'\"\r\n]*)?)(?P=quote)\s*\)",
))


def _origin(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _normalize_page_url(value: str, base_url: str) -> str:
    """Resolve a discovered navigation target and discard non-web/dynamic values."""
    value = html.unescape((value or "").strip())
    if not value or "${" in value or value.startswith(("#", "javascript:", "mailto:", "tel:")):
        return ""
    target = urldefrag(urljoin(base_url, value)).url
    return target if _origin(target) else ""


def _extract_script_navigation_urls(source: str, base_url: str) -> list[str]:
    """Extract literal destinations used by buttons and client-side routers."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _SCRIPT_NAVIGATION_PATTERNS:
        for match in pattern.finditer(source or ""):
            target = _normalize_page_url(match.group("url"), base_url)
            if target and target not in seen:
                seen.add(target)
                found.append(target)
    return found


def _extract_static_image_urls(source: str, base_url: str) -> list[str]:
    """Extract literal image paths that may only be assigned after interaction."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _STATIC_IMAGE_PATTERNS:
        for match in pattern.finditer(source or ""):
            target = _normalize_page_url(match.group("url"), base_url)
            if target and target not in seen:
                seen.add(target)
                found.append(target)
    return found


def _discover_page_targets(page, page_url: str) -> tuple[list[str], list[str]]:
    """Return ordinary DOM links and explicit script-driven navigation targets."""
    try:
        raw_links = page.eval_on_selector_all(
            "a[href], area[href], form[action], button[formaction], "
            "input[formaction], [data-href]",
            "els => els.map(e => e.href || e.action || e.formAction || e.dataset.href)",
        )
    except Exception:  # noqa: BLE001
        raw_links = []

    links: list[str] = []
    seen: set[str] = set()
    for value in raw_links:
        target = _normalize_page_url(value, page_url)
        if target and target not in seen:
            seen.add(target)
            links.append(target)

    try:
        source = page.content()
    except Exception:  # noqa: BLE001
        source = ""
    return links, _extract_script_navigation_urls(source, page_url)


def _in_scope(url: str, allowed_origins: set[str]) -> bool:
    return _origin(url) in allowed_origins


def _write_record(writer: WARCWriter, response, body: bytes, content_type: str) -> None:
    raw = response.request
    url = response.url

    # content-type은 (최적화로 바뀔 수 있어) 직접 다시 설정한다.
    skip = _SKIP_HEADERS | {"content-type"}
    headers = [(k, v) for k, v in response.headers.items() if k.lower() not in skip]
    if content_type:
        headers.append(("Content-Type", content_type))
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

    seed_url = _normalize_page_url(seed_url, seed_url)
    allowed_origins = {_origin(seed_url)}
    seen_resources: set[str] = set()
    visited_pages: set[str] = set()
    pages: list[dict] = []
    queue: list[tuple[str, int]] = [(urldefrag(seed_url).url, 0)]
    written = 0
    saved = 0

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

                    # Hidden screens often contain an empty <img> whose source is only
                    # assigned by JavaScript after clicking Next. Preload literal image
                    # paths so their responses are included in the WARC as well.
                    image_urls = _extract_static_image_urls(page.content(), page.url or url)
                    if image_urls:
                        page.evaluate(_PRELOAD_IMAGES, image_urls)
                        page.wait_for_timeout(200)
                except Exception as error:  # noqa: BLE001
                    print(f"    warn: {url} 로드 경고: {error}")

                pages.append({
                    "id": hashlib.sha1(url.encode()).hexdigest()[:16],
                    "url": url,
                    "title": page_title,
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })

                resource_scripted_links: list[str] = []
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
                    content_type = ""
                    for key, value in response.headers.items():
                        if key.lower() == "content-type":
                            content_type = value
                            break
                    original_len = len(body)
                    body, content_type = _optimize_image(content_type, body)
                    saved += original_len - len(body)
                    if (
                        "javascript" in content_type.lower()
                        and _in_scope(res_url, allowed_origins)
                    ):
                        resource_scripted_links.extend(
                            _extract_script_navigation_urls(
                                body.decode("utf-8", errors="replace"), res_url
                            )
                        )
                    try:
                        _write_record(writer, response, body, content_type)
                        written += 1
                    except Exception as error:  # noqa: BLE001
                        print(f"    warn: {res_url} 기록 실패: {error}")

                if level < depth:
                    links, scripted_links = _discover_page_targets(page, page.url or url)
                    for link in links:
                        if _in_scope(link, allowed_origins) and link not in visited_pages:
                            queue.append((link, level + 1))

                    # A literal location/window.open/router target is an explicit part of
                    # the work even when it lives on another host (for example a GitHub
                    # Pages intro that opens its Vercel app). Admit that origin, then let
                    # the normal depth/page limits bound any further crawl.
                    for target in scripted_links + resource_scripted_links:
                        target_origin = _origin(target)
                        if target_origin:
                            allowed_origins.add(target_origin)
                        if target not in visited_pages:
                            queue.append((target, level + 1))

            browser.close()

    return written, pages, saved


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
        count, pages, saved = _capture_to_warc(seed_url, warc_path, page_limit, depth)
        if count == 0:
            raise RuntimeError(f"{seed_url} 에서 기록된 응답이 없습니다.")
        saved_note = f", 이미지 최적화 {saved / 1024 / 1024:.1f}MB 절약" if saved > 0 else ""
        print(f"    {count}개 리소스, {len(pages)}개 페이지 기록{saved_note} → WACZ 패키징")

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
        if wacz_path.exists():  # 재캡처 시 기존 파일을 확실히 덮어쓴다
            wacz_path.unlink()
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
