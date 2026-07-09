# ID20012: Design Studio 1 Archive

Exploring Aesthetics and Form Giving  
KAIST Industrial Design / Spring 2026

학생 웹 작업물을 학기마다 장기 보존하는 정적 아카이브 파이프라인.

핵심 원칙: **WACZ/WARC 표준 포맷 + 서버 없는 재생 + 사람이 읽는 매니페스트 +
다중 백업.** GitHub Actions/Pages/Releases는 빠르게 시작하기 위한 MVP 도구이고,
장기 보존 원본은 GitHub 밖(학교/연구실 저장소, NAS, S3 호환 저장소 등)에
별도로 복제한다.

전체 설계와 운영 매뉴얼은 [docs/운영가이드.md](docs/운영가이드.md) 참고.

## 로컬 폴더용 간단 버전

서버, GitHub, 로그인 없이 Google Drive 폴더 안에서만 보여줄 때는 루트의
`index.html`과 `manifest.csv`를 같은 폴더에 두면 된다. 교수자나 조교가
`index.html`을 더블클릭하면 CSV를 읽어 목록을 만들고, 각 행을 누르면 CSV에 적힌
파일 경로나 URL을 연다.

브라우저 보안 정책 때문에 로컬 CSV 자동 읽기가 막히는 경우가 있다. 이때는 화면의
`CSV` 선택 버튼에서 같은 폴더의 `manifest.csv`를 한 번 골라 주면 된다.

로컬 인덱스가 우선해서 읽는 컬럼은 다음과 같다.

- 작품명: `title`, `work`, `name`
- 학생명: `student_name`, `student`, `author`
- 수업/학기: `semester`, `class`, `course`
- 열람 대상: `archive_file`, `file`, `path`, `local_file`, `wacz_file`, 없으면
  `url`, `original_url`, `link`
- 숨김 처리: `status`가 `private` 또는 `hidden`이면 목록에서 제외

## 구조

- `manifest.csv` — 단일 출처(single source of truth). 학생 한 명당 한 줄.
- `2026 design studio.numbers` — Spring 2026 제출 링크 원본 스프레드시트.
- `site/` — 빌드 단계 없는 정적 아카이브 사이트 (GitHub Pages 또는 아무 정적 서버).
- `site/replay/` — replayweb.page 런타임(`ui.js`, `sw.js`)을 버전 고정해 자가호스팅.
- `tools/` — 서드파티 의존성 없는 파이썬 스크립트.
- `.github/workflows/archive.yml` — 매니페스트 변경 시 자동 크롤링 → WACZ 생성 →
  체크섬 기록 → Releases 업로드 → Pages 재생용 사본 배포.

## 운영 워크플로우 (CSV → 자동 아카이브)

1. 학생에게서 로그인 없이 접근 가능한 **공개 URL**을 받는다.
2. Google Sheet에서 수집하되, `@보기`, `@캡쳐` 같은 태그 대신 `status`
   드롭다운을 쓴다.
3. 캡처 준비가 된 행은 `ready-to-capture`로 둔다. URL이 아직 없으면
   `pending`으로 둔다.
4. 최종 CSV를 내려받아 `tools/manifest-editor.html`에서 열고 오류를 검수한다.
5. `manifest.csv`에 반영한 뒤 커밋·푸시하면 Actions가 캡처 대상 행을 자동으로
   크롤링한다.
6. 캡처가 끝난 행은 자동으로 `review-needed`가 되고, `wacz_file`,
   `archived_date`, `sha256`이 채워진다.
7. 캡처된 작품을 ReplayWeb.page에서 직접 열어 재생 품질을 확인한 뒤
   `status`를 갱신한다. **캡처 성공과 재생 성공은 다르다** — 자동 캡처 직후
   상태는 `review-needed`이며, 사람이 확인해야 `ok`가 된다.
8. 그 학기 WACZ 묶음을 장기 저장소와 외부 백업에 복제한다(아래 백업 위치).

일상 운영에서는 GitHub Actions 화면을 직접 열 필요가 없다. `manifest.csv`가
크롤링 큐 역할을 한다.

### Google Sheet 편집 규칙

Google Sheet는 협업과 링크 수집용으로 계속 쓴다. 다만 자유 태그 대신 아래처럼
명시적인 컬럼을 유지한다.

```text
student_name,title,original_url,semester,wacz_file,wacz_url,archived_date,sha256,status,notes
```

`status` 컬럼은 데이터 유효성 검사 드롭다운으로 제한한다.

```text
pending
ready-to-capture
review-needed
ok
partial
recapture-needed
private
```

학기 말 또는 캡처 직전에는 Sheet에서 CSV를 내려받아
`tools/manifest-editor.html`을 브라우저로 열고 `Load CSV`로 불러온다. 기존
`@보기`, `@캡쳐` 태그가 남아 있으면 `Convert @ Tags`로 상태값으로 변환한 뒤
`Download CSV`로 저장한다.

## 첫 크롤링 테스트

처음에는 전체 학생을 한 번에 돌리지 말고, `manifest.csv`에서 테스트할 학생
1명만 `pending`으로 두고 나머지는 `review-needed` 또는 `private`처럼 캡처 대상이
아닌 상태로 둔다. 그 상태로 커밋·푸시하면 CSV에서 바로 한 명만 크롤링된다.

수동으로 테스트하고 싶다면 Actions 화면에서도 한 명만 실행할 수 있다.

1. GitHub 레포의 **Actions** 탭으로 간다.
2. **Archive student sites** workflow를 선택한다.
3. **Run workflow**를 누르고 아래처럼 입력한다.
   - `semester`: `2026-spring`
   - `mode`: `pending`
   - `match`: `Seohyeon Gu` 처럼 학생 이름 또는 작품 제목
   - `page_limit`: `30`
   - `depth`: `3`
4. 실행이 끝나면 GitHub Releases에 `.wacz` 파일이 올라가고,
   `manifest.csv`의 `wacz_file`, `archived_date`, `sha256`, `status`가 갱신된다.
5. 재생을 확인한 뒤 문제가 없으면 `status`를 `ok`로 바꾼다.

여러 명이 안정적으로 성공한 뒤 `match`를 비워 전체 pending 항목을 크롤링한다.

## 검수 상태값 (`status`)

| status | 의미 | 공개 여부 |
|---|---|---|
| `pending` | URL 대기 또는 아직 작업 전 | 숨김 |
| `ready-to-capture` | URL 있음, 다음 자동 캡처 대상 | 숨김 |
| `review-needed` | 자동 캡처는 됐지만 사람이 확인해야 함 | 목록에 표시, Review 재생 가능 |
| `ok` | 재생 확인 완료 | 공개 (재생 가능) |
| `partial` | 일부 리소스/인터랙션 누락 | 공개, `notes`에 주석 필수 |
| `recapture-needed` | 다시 캡처해야 함 (다음 실행 시 자동 재캡처) | 숨김 |
| `private` | 학생 요청/저작권/개인정보 문제 | 비공개 (캡처·색인 모두 제외) |

빈 status는 `pending`과 동일하게 취급한다. 자동 캡처 대상은
`ready-to-capture`, `recapture-needed`, 그리고 과거 호환을 위한 빈 값/`pending`
행이다.

## 인수인계 안내

담당자(교수님/조교)가 바뀔 때 아래 네 가지만 채워서 넘기면 된다.

- **(a) 계정 접근**: 이 레포를 소유한 GitHub 계정/조직과 접근 권한 위치를
  여기에 기록한다. 개인 계정보다 수업용 조직 계정을 권장.
- **(b) 매니페스트에 줄 추가하는 법**: 위 운영 워크플로우 2번. GitHub 웹
  화면에서 `manifest.csv`를 바로 편집·커밋해도 된다.
- **(c) replayweb.page 고정 버전**: `site/replay/`에 받아 둔 `ui.js`/`sw.js`의
  버전을 [site/replay/README.md](site/replay/README.md)에 기록한다. CDN을 쓰지
  않으므로 업스트림이 바뀌어도 사이트는 동일하게 동작한다.
- **(d) 백업 위치**: WACZ 원본을 복제해 둔 곳(학교/연구실 저장소, NAS,
  객체저장소, Internet Archive 등)을 여기에 기록한다. 3-2-1 규칙: 최소 3벌,
  2종류 매체, 1벌은 외부에.

## 장기 보존 메모

- 각 WACZ의 SHA-256 체크섬이 매니페스트에 기록된다. 1년에 한 번 같은
  해시인지 확인(fixity 점검)하고, 다르면 백업본과 비교한다.
- GitHub Releases는 장기 보관/다운로드용 사본이고, GitHub Pages에는 재생을 위한
  같은 출처(`site/wacz/`) 사본이 배포된다. 브라우저 재생기는 CORS 제한 때문에
  Release 다운로드 URL을 직접 읽지 못할 수 있다.
- 저장 위치를 옮기면 매니페스트의 `wacz_url` 또는 빌드 환경의
  `ARCHIVE_PUBLIC_WACZ_BASE`를 바꾸면 된다.
- 자동 크롤링이 약한 인터랙티브 작품은 ArchiveWeb.page로 수동 캡처해 같은
  WACZ로 이 파이프라인에 넣을 수 있다.
