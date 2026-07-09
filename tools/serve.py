#!/usr/bin/env python3
"""HTTP Range 요청을 지원하는 최소 정적 서버 (표준 라이브러리만 사용).

replayweb.page는 큰 WACZ를 통째로 받지 않고 '구간 요청(HTTP Range)'으로
필요한 부분만 읽는다. 파이썬 기본 `http.server`는 Range를 지원하지 않아
큰 파일에서 "lack of range request support" 오류가 난다. 이 서버는 Range를
처리(206 Partial Content)해 큰 WACZ도 재생되게 한다.

사용: python3 tools/serve.py [PORT] [DIR]
"""

from __future__ import annotations

import http.server
import os
import sys


class _LimitReader:
    """감싼 파일에서 정확히 length 바이트만 읽어 주는 래퍼."""

    def __init__(self, fp, length):
        self.fp = fp
        self.remaining = length

    def read(self, size=-1):
        if self.remaining <= 0:
            return b""
        if size is None or size < 0 or size > self.remaining:
            size = self.remaining
        data = self.fp.read(size)
        self.remaining -= len(data)
        return data

    def close(self):
        self.fp.close()


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        try:
            stat = os.fstat(f.fileno())
            size = stat.st_size
            ctype = self.guess_type(path)
            rng = self.headers.get("Range")

            if not rng:
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(size))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
                self.end_headers()
                return f

            # "bytes=start-end" 파싱 (suffix range "bytes=-N"도 지원)
            try:
                unit, _, spec = rng.partition("=")
                if unit.strip().lower() != "bytes":
                    raise ValueError
                start_s, _, end_s = spec.strip().partition("-")
                if start_s == "":
                    length = int(end_s)
                    start = max(0, size - length)
                    end = size - 1
                else:
                    start = int(start_s)
                    end = int(end_s) if end_s else size - 1
                if start > end or start >= size:
                    raise ValueError
                end = min(end, size - 1)
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                f.close()
                return None

            length = end - start + 1
            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            f.seek(start)
            return _LimitReader(f, length)
        except Exception:
            f.close()
            raise

    def log_message(self, *args):
        pass  # 조용히 (창을 깔끔하게)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8817
    if len(sys.argv) > 2:
        os.chdir(sys.argv[2])
    with http.server.ThreadingHTTPServer(("", port), RangeHandler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
