#!/bin/zsh
# 보기 — 더블클릭으로 실행. 로컬 서버를 띄우고 브라우저로 아카이브를 연다.
# (WACZ 재생은 서비스워커를 쓰므로 로컬 서버가 필요하다. 파일을 직접 열면 재생이 안 된다.)
cd "$(dirname "$0")"

PORT=8817
URL="http://localhost:${PORT}/index.html"

echo "════════════════════════════════════════════"
echo "   archivve — 아카이브 보기"
echo "════════════════════════════════════════════"
echo
echo "브라우저가 곧 자동으로 열립니다."
echo
echo "⚠️  다 볼 때까지 이 검은 창을 닫지 마세요."
echo "    (이 창을 닫으면 사이트가 꺼집니다. 다 보면 그때 닫으세요.)"
echo
echo "직접 열려면 브라우저 주소창에: ${URL}"
echo

# 서버가 뜬 뒤 브라우저를 연다.
( sleep 1; open "$URL" ) &

# 서버 실행 — 창이 열려 있는 동안 유지된다.
# (기본 http.server 대신 Range 지원 서버. 큰 WACZ 재생에 Range가 필요하다.)
python3 tools/serve.py "$PORT" >/dev/null 2>&1 || {
  echo
  echo "이미 다른 '보기' 창이 열려 있는 것 같습니다."
  echo "브라우저에서 ${URL} 를 직접 열어 보세요."
  read "?엔터를 누르면 이 창을 닫습니다."
}
