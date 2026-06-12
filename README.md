# ID20012: Design Studio 1 Archive

Exploring Aesthetics and Form Giving  
KAIST Industrial Design / Spring 2026

학생 웹 작업물을 학기마다 장기 보존하는 정적 아카이브 파이프라인.

핵심 원칙: **WACZ/WARC 표준 포맷 + 서버 없는 재생 + 사람이 읽는 매니페스트 +
다중 백업.** GitHub Actions/Pages/Releases는 빠르게 시작하기 위한 MVP 도구이고,
장기 보존 원본은 GitHub 밖(학교/연구실 저장소, NAS, S3 호환 저장소 등)에
별도로 복제한다.

전체 설계와 운영 매뉴얼은 [docs/운영가이드.md](docs/운영가이드.md) 참고.

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
2. `manifest.csv`에 한 줄 추가한다: 이름, 제목, URL, 학기(예: `2026-spring`).
3. `status`를 비워 두거나 `pending`으로 둔다.
4. 커밋·푸시하면 Actions가 `manifest.csv`를 읽고 pending 행만 자동으로 크롤링한다.
5. 캡처가 끝난 행은 자동으로 `review-needed`가 되고, `wacz_file`,
   `archived_date`, `sha256`이 채워진다.
6. 캡처된 작품을 ReplayWeb.page에서 직접 열어 재생 품질을 확인한 뒤
   `status`를 갱신한다. **캡처 성공과 재생 성공은 다르다** — 자동 캡처 직후
   상태는 `review-needed`이며, 사람이 확인해야 `ok`가 된다.
7. 그 학기 WACZ 묶음을 장기 저장소와 외부 백업에 복제한다(아래 백업 위치).

일상 운영에서는 GitHub Actions 화면을 직접 열 필요가 없다. `manifest.csv`가
크롤링 큐 역할을 한다.

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
| `ok` | 재생 확인 완료 | 공개 (재생 가능) |
| `review-needed` | 자동 캡처는 됐지만 사람이 확인해야 함 | 목록에 표시, Review 재생 가능 |
| `partial` | 일부 리소스/인터랙션 누락 | 공개, `notes`에 주석 필수 |
| `recapture-needed` | 다시 캡처해야 함 (다음 실행 시 자동 재캡처) | 숨김 |
| `private` | 학생 요청/저작권/개인정보 문제 | 비공개 (캡처·색인 모두 제외) |

빈 status 또는 `pending`은 아직 캡처 전이라는 뜻이며 다음 실행 때 캡처된다.

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
