#!/bin/zsh
# 캡처 — 더블클릭으로 실행. 구글 시트의 새 학생을 가져와, 아직 캡처 안 된 작품을 저장한다.
cd "$(dirname "$0")"

echo "════════════════════════════════════════════"
echo "   archivve — 웹 작업물 캡처"
echo "════════════════════════════════════════════"
echo

# ── 1. 캡처 도구 확인 (처음이면 설치 제안) ─────────────────────
if ! python3 -c "import playwright, warcio, wacz, PIL" 2>/dev/null; then
  echo "처음이시네요. 캡처에 필요한 도구를 먼저 설치해야 합니다."
  echo "(약 2~3분 걸리고 인터넷이 필요합니다.)"
  echo
  read "ans?지금 설치하려면 엔터, 그만두려면 n 입력 후 엔터: "
  if [[ "$ans" == n* || "$ans" == N* ]]; then
    echo "설치를 취소했습니다."
    exit 0
  fi
  echo
  echo "설치 중... (창을 닫지 마세요)"
  if python3 -m pip install --quiet --upgrade playwright warcio wacz pillow && python3 -m playwright install chromium; then
    echo "설치 완료!"
    echo
  else
    echo
    echo "자동 설치에 실패했습니다. 터미널에 아래 두 줄을 붙여넣어 직접 실행해 주세요:"
    echo "    python3 -m pip install playwright warcio wacz pillow"
    echo "    python3 -m playwright install chromium"
    echo
    read "?엔터를 누르면 창을 닫습니다."
    exit 1
  fi
fi

# ── 2. 구글 시트에서 새 학생 가져오기 ─────────────────────────
echo "1) 구글 시트에서 새로 접수된 학생을 확인합니다..."
python3 tools/sync_manifest.py || echo "   (시트를 못 읽어 기존 목록으로 진행합니다.)"
echo

# ── 3. 캡처할 대상 파악 ──────────────────────────────────────
tally=$(python3 - <<'PY'
import csv
names = []
try:
    for r in csv.DictReader(open("manifest.csv")):
        s = r.get("status", "").strip().lower()
        if r.get("original_url", "").strip() and s in ("", "pending", "ready-to-capture", "recapture-needed"):
            names.append(r.get("student_name", "").strip() or r.get("title", "").strip() or "제목없음")
except FileNotFoundError:
    pass
print(len(names))
for nm in names:
    print("   · " + nm)
PY
)
count=$(printf '%s\n' "$tally" | head -1)
list=$(printf '%s\n' "$tally" | tail -n +2)

if [[ "$count" == "0" ]]; then
  echo "새로 캡처할 작품이 없습니다. (이미 모두 캡처됨)"
  echo
  echo "새 학생을 추가하려면 → 구글 시트에 이름·수업·링크를 넣고 이 파일을 다시 더블클릭하세요."
  echo "특정 학생을 다시 캡처하려면 → manifest.csv에서 그 학생 status를 recapture-needed로 바꾸고 다시 실행하세요."
  echo
  read "?엔터를 누르면 창을 닫습니다."
  exit 0
fi

echo "2) 캡처할 작품 ${count}개:"
printf '%s\n' "$list"
echo
read "go?이대로 캡처하려면 엔터, 그만두려면 n 입력 후 엔터: "
if [[ "$go" == n* || "$go" == N* ]]; then
  echo "취소했습니다."
  read "?엔터를 누르면 창을 닫습니다."
  exit 0
fi

# ── 4. 캡처 실행 ─────────────────────────────────────────────
echo
echo "3) 캡처 중입니다. 작품당 20초~1분 정도 걸립니다. 창을 닫지 마세요..."
echo
python3 tools/crawl_manifest.py --mode pending --out-dir wacz

# ── 5. 마무리 ───────────────────────────────────────────────
echo
echo "════════════════════════════════════════════"
echo "   끝났습니다!  '보기.command'를 더블클릭해 확인하세요."
echo "════════════════════════════════════════════"
echo
read "?엔터를 누르면 창을 닫습니다."
