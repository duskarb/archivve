# archivve — 수업 웹 아카이브

학생들의 웹 작업물을 **10~20년 장기 보존**하는 아주 단순한 아카이브 도구.

핵심은 하나다: **이 폴더가 곧 아카이브다.** 폴더 안에 목록 페이지(index.html),
명단(manifest.csv), 아카이브 파일(wacz/), 재생기(replay/)가 다 들어 있다.
외부 서비스에 의존하지 않으므로 USB나 드라이브에 복사해 두면 그대로 보존된다.
파일 포맷은 WACZ/WARC(웹 아카이브 국제표준 ISO 28500)라 먼 미래에도 열 수 있다.

---

## 역할 분담

- **구글 시트 = 접수함.** 새 학생의 **이름·수업·링크**만 넣는 곳. 학생에게 직접 채우게 해도 된다.
- **manifest.csv = 관리 원본.** 캡처 결과·상태·메모 등 모든 관리는 여기서 한다. 편집은 Numbers·Excel·텍스트, 또는 `tools/manifest-editor.html`로 한다.

`캡처.command`가 시트의 **새 학생만** manifest.csv로 가져오고(pending으로 추가),
이미 있는 학생의 관리 데이터는 절대 건드리지 않는다. 그래서 두 곳이 안 싸운다.

## 평소 사용법 — 3단계

### 1. 접수 (구글 시트)
[manifest 시트](https://docs.google.com/spreadsheets/d/1ttG_2q0ZKYopjJmkPUF9S3d3azgE8ymeFPboMheGVig/edit)에
새 학생을 한 줄 추가한다. 필요한 칸은 셋뿐:

| 칸 | 예시 |
|---|---|
| `student_name` | Jane Doe |
| `semester` | 2027-spring |
| `original_url` | https://jane-doe.github.io/project/ |

`semester`가 학기(또는 수업) 구분이다. 새 수업이 추가돼도 새 `semester`
이름만 적으면 된다. 폴더는 캡처할 때 자동으로 만들어진다.

### 2. 관리 (manifest.csv)
상태·제목·메모 등 운영 관리는 `manifest.csv`에서 한다. Google Sheet는 접수함으로
두고, `@보기`, `@캡쳐` 같은 자유 태그 대신 `status` 값을 명시적으로 쓴다.

로컬 폼이 편하면 브라우저에서 `tools/manifest-editor.html`을 열어 CSV를 불러온다.
`Load CSV`로 열고, 기존 태그가 남아 있으면 `Convert @ Tags`로 상태값으로 바꾼 뒤
`Download CSV`로 저장한다.

### 3. 캡처 (`캡처.command` 더블클릭)
시트에서 새 학생을 가져온 뒤, **캡처할 작품 목록을 보여주고 엔터 한 번**이면
캡처 대상 작품을 `wacz/<학기>/`에 저장한다. Docker도, 로그인도, 토큰도 필요 없다.
처음 실행 시 캡처 도구 설치를 물어보고 자동으로 깔아준다.

> 특정 학생을 다시 캡처하려면 `manifest.csv`에서 그 학생 `status`를
> `recapture-needed`로 바꾸고 다시 실행하면 된다.

### 4. 보기 (`보기.command` 더블클릭)
로컬 서버를 띄우고 브라우저로 아카이브 목록을 연다. 각 항목의 **Archive** 버튼을
누르면 보존된 사이트가 그대로 재생된다.

> `index.html`을 직접 더블클릭하지 말 것. 재생(WACZ)이 서비스워커를 쓰기 때문에
> 반드시 `보기.command`로 로컬 서버를 통해 열어야 재생된다.

---

## 최초 1회 준비 (캡처하는 Mac에서만)

캡처에는 파이썬 도구가 필요하다. 한 번만 설치한다:

```bash
python3 -m pip install playwright warcio wacz pillow
python3 -m playwright install chromium
```

*보기*는 macOS에 기본 내장된 python만 있으면 되므로 추가 설치가 필요 없다.

처음 `.command` 파일을 더블클릭하면 "확인되지 않은 개발자" 경고가 뜰 수 있다.
그럴 땐 파일을 **우클릭 → 열기**를 한 번만 하면 이후로는 그냥 더블클릭된다.

---

## 폴더 구조

```text
archivve/
├── index.html      목록/관리 현황 (Public list / All rows 모드)
├── viewer.html     Archive 버튼을 눌렀을 때 열리는 재생 전용 페이지
├── manifest.csv    관리 원본 (모든 상태·결과가 여기 있음)
├── replay/         재생기 런타임 (replayweb.page, 벤더링됨)
├── wacz/<학기>/     아카이브 파일 (.wacz)
├── 캡처.command     명단 갱신 + 캡처
├── 보기.command     로컬 서버 + 브라우저 열기
└── tools/          파이썬 도구와 로컬 manifest 편집기
```

---

## 백업 (중요)

저장 매체가 이 폴더 하나이므로, **폴더를 USB나 드라이브에 통째로 복사**해
사본을 한 벌 이상 보관한다. WACZ는 자족적 파일이라 복사만으로 보존된다.
학기말마다 한 번씩 복사해 두면 충분하다.

## 상태(status) 값

| status | 의미 | 공개 목록 |
|---|---|---|
| `pending` | URL 대기 또는 아직 캡처 전 | 숨김 |
| `ready-to-capture` | URL 있음, 다음 캡처 대상 | 숨김 |
| `review-needed` | 캡처 완료, 사람이 재생 확인 필요 | 숨김 |
| `ok` | 검수 완료 | 공개 |
| `partial` | 일부 누락 있지만 공개 가능 | 공개 |
| `recapture-needed` | 다시 캡처 필요 | 숨김 |
| `private` / `hidden` | 비공개 | 숨김 |

빈 status는 `pending`과 동일하게 취급한다. `캡처.command`는 빈 값, `pending`,
`ready-to-capture`, `recapture-needed`를 캡처 대상으로 본다. 캡처가 끝나면
`review-needed`가 되며, 사람이 재생을 확인한 뒤 `ok` 또는 `partial`로 바꾼다.

## 참고

- 자동 캡처가 약한 인터랙티브 작품은 [ArchiveWeb.page](https://webrecorder.net/archivewebpage)로
  수동 캡처해, 파일명을 `wacz/<학기>/<slug>.wacz` 규칙에 맞춰 넣어도 된다.
- 재생기(replay/)는 서비스워커 기반이라 먼 미래에 브라우저가 못 돌릴 수 있지만,
  WACZ 안의 WARC는 표준이라 그때의 어떤 도구로든 다시 열 수 있다. 원본 WACZ를
  잘 보관하는 것이 가장 중요하다.
