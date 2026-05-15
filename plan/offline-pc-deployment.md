# 동료 PC(Windows · Drive 차단) 배포 전략 기획서

> 작성일: 2026-05-15 · 작성자: upgrade-planner 에이전트
> 산출물: 계획서 1건 (코드 변경 없음, 커밋·푸시 없음)
> 대상 독자: 메인 세션 오케스트레이터, 후속 `code-modifier` / `integration-tester`, 그리고 배포 받을 동료

---

## 0. TL;DR (한 화면 요약)

| 항목 | 결론 |
|---|---|
| 가장 큰 차단 요소 | **Drive 차단은 더 이상 차단 요소가 아님** (2026-05-15 커밋으로 Drive/NotebookLM 의존 제거 완료). 실제 차단점은 `features.git_autosync`, A'(industry-scan)이 요구하는 prism repo 외부 의존, Windows 스케줄러 XML의 SID/경로 하드코딩. |
| 동료 요구 범위 | **최소 시나리오**: Focus 탭에서 수동 기사·PDF 보고서 첨부 → Weekly 또는 Focus 뉴스레터 생성 → Gmail 발송. Daily 자동 크롤링은 불요. |
| 추천 배포안 | **안 B (Portable venv + 동봉 zip + Windows 작업 스케줄러는 선택)**. Docker / PyInstaller 는 동료가 받아들이기 어렵고, 본 시스템은 인터프리터 호출만 있으면 충분. |
| AI 운영 환경 이식 | **코드 배포와 분리**. `.claude/agents/*.md` 는 Claude Code(또는 호환 CLI) 환경에서만 의미. 동료가 동일 워크플로를 쓰려면 Claude Code CLI 또는 Coworker 호환 도구가 필요. 없다면 일반 CLI + README 흐름. |
| 합격 기준 핵심 | 동료 PC에서 (1) `python main.py --mode server` 가 60초 내 200 OK, (2) Focus 탭 수동 기사 추가 후 5분 내 Gmail 발송 성공, (3) 인터넷 차단 환경(Drive 도메인 차단)에서 발송 흐름이 **fail-fast 없이** 완료. |

---

## 1. 배경 / 목표 / 비목표

### 1.1 배경
- 본 시스템은 SPRi 산업분석팀의 운영 도구로, 현재 1명의 전문가 PC(`C:\Users\martin.hs.yoo\dev\newsletter_system`)에서 단독 운영 중.
- 운영 백업·전문가 부재 대응을 위해 동료 PC로의 **이식 가능성**을 확보해야 함.
- 동료 PC는 Windows 10/11, Anthropic·Gmail 접근 가능, **Google Drive 만 차단**.

### 1.2 목표
1. 동료가 자기 PC에서 **최소 시나리오**(Focus 수동 큐레이션 → Gmail 발송)를 30분 이내 셋업할 수 있다.
2. 본 시스템의 **Drive 외 외부 의존**을 명시적으로 정리하여, 향후 사내망 변경에도 영향도가 예측 가능하다.
3. AI 보조 작업(`.claude/agents/*`)이 있는 사람과 없는 사람 모두 운영 가능하도록 **두 경로**를 마련한다.

### 1.3 비목표 (이번 기획서 범위 밖)
- A'(industry-scan, prism 4-Pass) 자동화의 풀 이식 — prism repo·MCP·외부 5개 API 키까지 모두 동료에게 넘기는 것은 별도 과제.
- 사내 PyPI / 사내 CA / 그룹 정책(GPO) 단위 자동 배포.
- 멀티 사용자 동시 발송 동기화 (현 `git_sync` 가 단일 공유 계정 + 단일 활성 발송자를 가정).
- Mac/Linux 환경 — 본 기획서는 Windows 단일 OS 가정.

---

## 2. 외부 서비스 의존 매트릭스

(2026-05-15 기준 코드 상태를 기준으로 작성. Drive/NotebookLM 통합은 이미 제거됨.)

| 서비스 | 호출 위치 | 필수/선택 | 차단 시 동작 | 동료 PC 영향 | 우회/대안 |
|---|---|---|---|---|---|
| **Anthropic Claude API** | `src/claude_service.py`(generate_daily/weekly/focus, summarize_report_text), `scripts/run_industry_scan.py` | 필수 | 본문 생성 실패 → `_fallback_articles_markdown` 또는 발송 차단 | 접근 가능 → 영향 없음 | n/a |
| **GNews API** | `src/news_service.py` | A 모드일 때만 필수 (Daily). Focus/Weekly 수동 큐레이션에는 **불요** | Daily 발송 실패 | 최소 시나리오에선 호출 안 됨 | API 키 미발급도 OK (Focus만 쓰면 됨) |
| **Gmail API (OAuth2)** | `src/gmail_service.py`(send_email, search_sent_today), `src/google_auth.py` | 필수 (모든 발송, dedup) | 발송 실패 + dedup CSV fallback | 접근 가능 → 영향 없음. **OAuth 동의 화면 첫 통과는 동료 본인의 브라우저 필요** | `features.gmail_dedup: false` 로 dedup 비활성 가능 |
| **Google Drive / Docs API** | (없음) | — | — | **이미 제거됨** — 차단되어도 무영향 | n/a |
| **Google NotebookLM (notebooklm-py)** | (없음) | — | — | 이미 제거됨 | n/a |
| **prism repo + prism-data MCP (Naver/Tavily/Guardian/data.go.kr/OpenDart)** | `src/industry_scan_service.py` → `scripts/run_industry_scan.py` → `c:/Users/martin.hs.yoo/dev/prism` | A' 모드일 때만 필수 | `IndustryScanError` → A 모드 자동 폴백 (config의 `news_mode_fallback_on_failure: true`) | **동료 PC엔 prism 미설치 → 자동 A 모드 폴백**. 그러나 Focus 최소 시나리오에선 호출되지 않음 | 동료 PC는 `news_mode: gnews` 로 명시 권장 |
| **git remote (origin)** | `src/git_sync.py` (`pull_or_fail`, `commit_and_push`), `main.py` daily, `web_ui/app.py` weekly/focus publish | 선택 | `features.git_autosync: false` 면 no-op, 또는 remote 없으면 자동 skip | 동료 PC에서 사내 git remote 미설정이면 자연스럽게 skipped | `features.git_autosync: false` 로 끄는 것 권장 (최소 시나리오) |
| **URL 메타데이터 / PDF 외부 다운로드** | `web_ui/app.py:extract_url_metadata`, `src/manual_reports.py:download_pdf` | Focus 첨부 시 선택 | 첨부 실패 (사용자가 다른 자료로 재시도) | 동료가 첨부하려는 도메인이 차단되면 그 자료만 실패 | PDF 파일 직접 업로드 경로(`multipart/form-data file`)는 인터넷 불요 |

### 2.1 Google OAuth scope 확정값
- 파일: `src/google_auth.py:20-23`
- 현재 scope: `gmail.send`, `gmail.readonly` (Drive/Docs scope 모두 제거됨)
- → 동료 OAuth 동의 화면에서 "Gmail 보내기 + Gmail 읽기" 2개만 노출. Drive 권한 요구 없음 → 사내 보안팀 승인 부담 ↓

### 2.2 시크릿/인증 파일 매트릭스
| 파일 | 생성/획득 방법 | 동료 PC 전달 방법 권장 | 비고 |
|---|---|---|---|
| `.env` | `.env.example` 복사 후 수기 입력 | 동료가 자기 키 발급/입력 — 메인 PC 키 공유 금지 | `CLAUDE_API_KEY` 필수, `GNEWS_API_KEY` 는 A 모드만 필요 |
| `credentials/google_credentials.json` | Google Cloud Console → OAuth2 Desktop client | **공용 Google Cloud 프로젝트의 동일 OAuth Client를 공유**하거나, 동료가 자기 프로젝트 만들고 자기 client 발급 (둘 다 가능) | 파일 자체엔 secret 포함, 사내 권고는 USB/암호화 채널 |
| `credentials/google_token.json` | `google_auth.py:get_google_credentials` 첫 실행 시 브라우저 OAuth 동의 후 자동 생성 | **동료 PC에서 새로 발급** (메인 PC 토큰 복사 금지) | refresh_token 포함 |

---

## 3. Drive 차단 영향 분석

### 3.1 결론
**현 코드 기준 영향 0.** Drive 도메인(`drive.google.com`, `docs.google.com`)이 차단되어도 다음을 확인했다:

| 확인 항목 | 결과 |
|---|---|
| `grep -rn drive\|notebooklm src/ main.py web_ui/app.py` | 모두 **주석/로그 문자열**뿐. 실제 API 호출 없음. (`main.py:71-72` 의 docstring, `web_ui/app.py:362,797` 의 주석/comment, `db.py:369` 의 마이그레이션 노트). |
| `requirements.txt` | Drive/Docs 클라이언트 패키지 없음. `google-api-python-client` 는 Gmail용으로만 사용. |
| OAuth scope | Drive scope 없음 (§2.1). |
| `newsletter_log.csv` 헤더 | 코드 상 헤더는 `drive_doc_id` 미포함 (`src/db.py:41-44`). 단, **기존 CSV 파일에 잔존 컬럼**(`drive_doc_id, nlm_notebook`)이 있음. → DictWriter 호환성 점검 필요 (Step 0). |
| Web UI 라우트 | `/focus/publish`, `/weekly/publish` 모두 Gmail + 로컬 백업 + git_sync 만 호출. Drive 호출 없음. |

### 3.2 만약 향후 Drive 재도입을 막아야 한다면 (방어 계획)
이건 동료 PC 안전망. 사내 정책이 더 엄격해질 때 대비.

| 대체 저장소 | 적합도 (Drive 차단 시) | 비고 |
|---|---|---|
| 로컬 디스크 (`data/newsletters/*.md`) | ★★★★★ | 이미 `_save_local_backup` 으로 수행 중. 사실상 기본. |
| Git 원격(사내 GitLab/GitHub) | ★★★★ | `git_sync` 가 이미 구현. 동료/팀 공유에도 효과적. 단 사내 git 권한 필요. |
| 사내 파일 서버(SMB) | ★★★ | `data/newsletters/` 를 매핑된 네트워크 드라이브로 심볼릭 링크. 코드 변경 없음. |
| OneDrive / SharePoint (사내 M365) | ★★★ | OneDrive 폴더에 `data/newsletters/` 위치. 동기화는 OS가 담당. 코드 변경 없음. |
| S3 호환(MinIO 등) | ★★ | 새 클라이언트 + 키 관리 추가. 본 시스템엔 과한 옵션. |
| Git LFS | ★ | 보고서 .md 는 LFS 불요. PDF 보관에만 의미, 그러나 PDF는 어차피 로컬 보관. |

→ **권장**: 로컬 디스크 + (가능하면) 사내 git remote. 추가 코드 변경 불요.

---

## 4. 배포 시나리오 비교 (4안)

각 안에 패키징·설치·시크릿·데이터·스케줄러·업데이트·트레이드오프를 표로 정리.

### 안 A: 사용자 git clone + 시스템 Python + venv (개발자 친화형)
| 항목 | 내용 |
|---|---|
| 패키징 | repo 그대로. 동료가 `git clone` |
| 설치 | (1) Python 3.11+ 설치, (2) `git clone`, (3) `python -m venv .venv`, (4) `.venv\Scripts\activate`, (5) `pip install -r requirements.txt`, (6) `.env`/`credentials/` 배치 |
| 시크릿 전달 | 동료 본인이 별도 채널로 받음 (USB/Bitwarden/사내 메신저 암호화 첨부) |
| 데이터 시드 | `data/db/*.csv` 헤더만 있는 빈 파일로 시작. 또는 메인 PC `manual_reports.csv` 비식별화 후 일부 시드 |
| 스케줄러 | 동료 사용 빈도가 낮으면 수동(`python main.py --mode server` 만 띄움). 자동화 원할 때만 작업 스케줄러 등록 |
| 업데이트 | `git pull` |
| 장점 | (1) 코드 가시성, (2) 디버깅·재발급 쉬움, (3) `claude/agents` 그대로 사용 가능 |
| 단점 | Python·git·pip 사용에 익숙해야 함. 사내 PC에 Python·git 설치 권한 필요 |
| 권장 사용처 | **개발자 동료 / 백업 운영자** |

### 안 B: Portable venv + 동봉 zip (권장)
| 항목 | 내용 |
|---|---|
| 패키징 | 메인 PC에서 (1) `python -m venv .venv-win`, (2) `pip install -r requirements.txt`, (3) `.venv-win/` 까지 통째로 zip. 더 보수적으론 `embeddable Python`(python-3.11.x-embed-amd64.zip) + `get-pip` + 의존성 wheel을 동봉 |
| 설치 | (1) zip 압축 해제, (2) 동봉된 `setup_local.bat` 더블클릭 (.env 입력 가이드 + 첫 OAuth 트리거) |
| 시크릿 전달 | `.env.example` 동봉. 동료는 첫 실행 시 자기 키 입력. OAuth는 첫 `--mode server` 에서 브라우저 자동 오픈 |
| 데이터 시드 | 빈 CSV(헤더만). `data/manual_reports/` 빈 디렉토리 |
| 스케줄러 | Focus 최소 시나리오에선 불필요. 자동 Daily 원하면 동봉된 `register_task.bat` (수정판) 사용 |
| 업데이트 | 메인 운영자가 새 zip 배포 또는 `git pull`(개발자 동료에 한함) |
| 장점 | (1) 동료 PC에 Python 설치 권한 없어도 됨, (2) 의존성 핀 고정, (3) Drive 차단/network proxy 신경 안 씀 (이미 wheel 동봉) |
| 단점 | zip 크기 ~150MB (PyMuPDF 미포함 시 더 작음, 현재 deps는 가벼움), 의존성 보안 업데이트 시 zip 재배포 필요 |
| 권장 사용처 | **본 기획서의 추천 안 — 동료가 비개발자거나, 사내 PC가 Python 직접 설치 까다로울 때** |

### 안 C: PyInstaller `--onefile` 실행 파일
| 항목 | 내용 |
|---|---|
| 패키징 | `pyinstaller --onefile main.py` (Flask 정적/템플릿 path 핸들링 별도) |
| 설치 | `SPRiNewsletter.exe` 더블클릭 + `.env`/`credentials/` 같은 폴더 배치 |
| 시크릿 전달 | 동일 (별도 채널) |
| 데이터 시드 | exe 옆에 `data/` 폴더 자동 생성 |
| 스케줄러 | exe 직접 등록 가능 |
| 장점 | 동료에게 가장 단순. "더블클릭만 하면 됨" |
| 단점 | (1) Flask + Jinja 템플릿/static 경로 hidden import 디버깅 부담, (2) `pdfplumber`(pdfminer.six C-extension 포함), `anthropic`, `mcp` 등 ~hidden imports 손볼 곳 많음, (3) Antivirus 오탐 빈발 (사내 EDR 격리 사례 흔함), (4) 코드 수정 시 재패키징 cycle, (5) `.claude/agents` 워크플로 의미 없어짐 |
| 권장 사용처 | 비개발자에 한정 + 동결된 버전. 본 시스템처럼 변경 잦은 운영툴엔 부적합 |

### 안 D: Docker Desktop + WSL2
| 항목 | 내용 |
|---|---|
| 패키징 | `Dockerfile` + `docker-compose.yml`. Gmail OAuth 콜백 위한 host 네트워크 노출 |
| 설치 | Docker Desktop 설치(라이선스 / 사내 정책 이슈 잦음), `docker compose up` |
| 시크릿 전달 | bind mount or `.env` |
| 장점 | 환경 격리 완벽, OS 무관 |
| 단점 | (1) Docker Desktop 사내 라이선스/설치 권한 이슈, (2) WSL2 활성화 권한, (3) OAuth `run_local_server(port=0)` 의 브라우저 콜백을 host로 라우팅하는 추가 설정, (4) 사내 프록시 + Docker DNS 충돌 빈번 |
| 권장 사용처 | 동료가 이미 Docker Desktop 익숙 + 사내 정책 허용 시. 일반적이지 않음 |

### 비교 요약
| 기준 | A: clone+venv | **B: portable zip** | C: PyInstaller | D: Docker |
|---|---|---|---|---|
| 동료 진입장벽 | 중 | **낮음** | 매우 낮음(설치) ↔ 매우 높음(트러블슈팅) | 매우 높음 |
| Drive 차단 영향 | 없음 | 없음 | 없음 | 없음 |
| 사내 Python 설치 권한 필요? | 예 | 아니오 | 아니오 | 아니오 (Docker 권한 필요) |
| 업데이트 용이성 | 매우 높음 | 중 (zip 재배포) | 낮음 | 중 |
| 보안 정책 마찰 | 낮음 | 낮음 | 중(EDR 오탐) | 높음 |
| `.claude/agents` 그대로 사용 | 가능 | 가능 (Claude Code CLI 있으면) | 사실상 불가 | 가능 |
| 추천도 | ★★★★ | ★★★★★ | ★★ | ★★ |

---

## 5. 추천 안: B (Portable zip) + A 보조 경로

### 5.1 선정 근거
- 동료 요구가 **최소 시나리오**(Focus 수동 + Gmail 발송)에 집중 → 풀 자동화·풀 의존성 풀세트가 불필요. 풀 자동화 옵션(prism, A')은 메인 운영자만 유지.
- Drive 차단은 더 이상 차단점이 아니므로 **추가 코드 변경이 거의 없음** — 패키징·문서·기본값 변경에 집중하면 됨.
- 동료가 개발자/비개발자 어느 쪽이든 zip 안에서 "더블클릭" 또는 "venv 활성화 → 실행" 둘 다 가능.
- 향후 보강(코드 변경 시) 시에도 메인 운영자가 zip만 재패키징하면 됨.
- 안 A는 개발자 동료용 보조 경로로 함께 문서화.

### 5.2 추천 안의 패키지 구조 (동료가 받는 zip)
```
spri-newsletter-v<YYYYMMDD>/
├─ README_FIRST.txt                 # 30분 셋업 가이드 (한국어, 비개발자 친화)
├─ setup_local.bat                  # .env 입력 / OAuth 트리거 / 첫 server 기동
├─ start_server.bat                 # 일상 사용: python -m main --mode server
├─ stop_server.bat                  # 서버 종료 (taskkill PID 검색)
├─ register_task.bat                # (선택) Daily 자동화 작업 스케줄러 등록 — 수정판
├─ uninstall_task.bat               # (선택) 스케줄 해제
├─ python/                          # embeddable Python 3.11 (옵션 1) 또는 .venv-win (옵션 2)
├─ src/, web_ui/, scripts/, main.py # 본 repo의 코드 그대로
├─ config.yaml                      # `news_mode: gnews`, `git_autosync: false`, `recipients.focus: []` 보정값
├─ .env.example                     # 키 입력 템플릿
├─ credentials/                     # 비어 있음 (동료가 OAuth json 배치)
├─ data/db/                         # 헤더만 있는 빈 CSV 5개
├─ data/newsletters/                # 빈 디렉토리
├─ data/manual_reports/             # 빈 디렉토리
├─ docs/
│  ├─ DEPLOY_WINDOWS.md             # 본 기획서에서 발췌한 동료용 단축 가이드
│  ├─ FAQ_DRIVE_BLOCKED.md          # "Drive 차단인데 괜찮나요?" 안내
│  └─ TROUBLESHOOTING.md            # OAuth 콜백 포트, msvcrt 락, 한글 인코딩 등
└─ logs/                            # 빈 디렉토리 (.gitkeep)
```

---

## 6. 단계별 작업 목록 (추천 안 기준)

각 Step은 단일 책임 + 실패 시 롤백이 명확하도록 작성. **이 기획서는 코드를 수정하지 않음.** 아래 Step은 `code-modifier` 가 후속에서 실행할 항목.

### Step 0. CSV 헤더 호환성 회귀 확인 (선결, 코드 수정 없음 가능)
- 대상 파일 (조사만): `data/db/newsletter_log.csv`, `data/db/article_archive.csv`, `src/db.py:29-54`, `src/db.py:append_row / _read_rows`
- 변경 내용:
  - 메인 PC의 기존 CSV 헤더는 `..., drive_doc_id, nlm_notebook`(`newsletter_log.csv`), `..., nlm_notebook_id`(`article_archive.csv`) 가 잔존. 코드의 `SHEET_HEADERS` 는 이 컬럼 없음.
  - `code-modifier` 가 **헤더 마이그레이션 함수**(`_migrate_legacy_headers`) 를 `src/db.py:init_db` 직후에 추가하거나, 동료 zip 의 빈 CSV 는 새 헤더로 시작하도록 보장.
  - 권장: 동료 zip 에는 **새 헤더만** 들어간 빈 CSV 동봉. 메인 PC 의 마이그레이션은 별도 과제.
- 의존: 없음. 안전 점검용.

### Step 1. 동료 기본값 프로파일 도입 (`config.yaml` 변종)
- 대상 파일: `config.yaml` (또는 신규 `config.windows-portable.yaml`), `main.py:load_config`
- 변경 내용:
  - `features.news_mode: "gnews"` (A' 미설치 환경 가정)
  - `features.news_mode_fallback_on_failure: true`
  - `features.git_autosync: false` (동료 PC 는 사내 git remote 미설정 가정)
  - `features.gmail_dedup: true` 유지 (Gmail Sent 가 진실의 원천 → 멀티 PC 안전)
  - `recipients.focus: []` 키 **신규 추가** — 현재 미정의 → Focus 발송 시 `recipients=[]` 로 가서 `send_email` 가 `ValueError` 만 던짐. 동료 PC 에서 첫 사용 시 명확한 가이드 필요.
  - `recipients.daily`, `recipients.weekly` 는 빈 리스트로 시작 (동료가 자기 수신자 입력 가이드 받음)
  - 옵션: `main.py:load_config` 가 `SPRI_CONFIG` 환경변수로 config 파일 경로 override 가능하게 (`load_config()` 시그니처에 인자 추가 또는 env 우선).
- 의존: 없음.

### Step 2. Drive 흔적 청소 (선택, 가독성용)
- 대상 파일: `main.py:71-72`(docstring), `web_ui/app.py:362,797`(주석/코멘트), `src/google_auth.py:3`(docstring)
- 변경 내용:
  - docstring/주석에서 "Google Drive API → 구글 문서 생성 (Phase 5)" 같은 사라진 단계를 "(제거됨, 2026-05-15)" 로 일관 표기.
  - 동료 코드 리딩 시 혼란 방지.
- 의존: 없음. **기능 변경 없음** — `integration-tester` 는 본 Step 에 대해 pytest 통과만 확인.

### Step 3. Portable launcher 스크립트 도입 (Windows)
- 대상 파일 (신규):
  - `scripts/win/setup_local.bat`
  - `scripts/win/start_server.bat`
  - `scripts/win/stop_server.bat`
- 변경 내용:
  - `setup_local.bat`:
    1. `chcp 65001` (한글 깨짐 방지)
    2. `.env` 가 없으면 `.env.example` 복사 + 메모장 자동 오픈
    3. `credentials\google_credentials.json` 존재 여부 확인 (없으면 안내문 출력 + 중단)
    4. `python -m venv .venv` (이미 있으면 skip) → `pip install -r requirements.txt`
    5. 첫 `python main.py --mode server` 를 5초간 실행시켜 OAuth 브라우저 트리거 (`google_auth.py:run_local_server(port=0)` 가 콜백 → token.json 생성). 사용자에게 "브라우저에서 동의 후 이 창을 닫지 마세요" 안내.
  - `start_server.bat`: `python main.py --mode server` 단순 실행, 종료 시 자동 로그 출력.
  - `stop_server.bat`: 포트 5000 LISTEN PID 검색 후 `taskkill /F /PID`.
- 의존: Step 1 (`config.yaml` 기본값).
- 주의: Windows 의 `run_local_server(port=0)` 는 OAuth 콜백을 `localhost:<random>` 으로 받음 → 사내 방화벽이 localhost loopback 차단하지 않음을 사전 확인 필요 (FAQ 항목).

### Step 4. 작업 스케줄러 템플릿 (선택)
- 대상 파일:
  - `task_schedule.xml` → **삭제 또는 `task_schedule.template.xml`로 변경** (사용자 SID·하드코딩 경로 제거)
  - `register_task.bat` → 동료 PC 경로 자동 치환(`%~dp0`)으로 수정
  - `run_daily.bat` → 하드코딩 `C:\Users\martin.hs.yoo\dev\newsletter_system` 을 `%~dp0` 로 치환, `%PYEXE%` 를 `.venv\Scripts\python.exe` 또는 시스템 python 자동 탐색
- 변경 내용:
  - 동료가 폴더 위치를 바꿔도 정상 동작.
  - `task_schedule.template.xml` 에서 `<UserId>` 는 register 시점 환경변수 `%USERNAME%` 로 치환.
  - 동료 최소 시나리오에선 등록 불필요 — README 에 "수동 실행 권장, 자동화 원할 때만 실행" 표기.
- 의존: Step 1, 3.

### Step 5. 동봉 문서 작성
- 대상 파일 (신규):
  - `docs/DEPLOY_WINDOWS.md` — 30분 셋업 (스크린샷 placeholder 포함)
  - `docs/FAQ_DRIVE_BLOCKED.md` — "Drive 차단인데 메일 발송 됨? 예. 이유는…"
  - `docs/TROUBLESHOOTING.md` — OAuth 콜백, 한글 인코딩(chcp), pip SSL/사내 프록시, msvcrt 락 경합
- 변경 내용:
  - DEPLOY_WINDOWS.md 의 단계:
    1. Python 3.11 설치 (또는 동봉 embeddable 사용)
    2. zip 압축 해제 위치 선정 (한글 경로 회피)
    3. Google Cloud Console 에서 OAuth client 다운로드 → `credentials/google_credentials.json` 배치
    4. `.env` 에 Anthropic 키 입력
    5. `setup_local.bat` 더블클릭 → 브라우저 OAuth 동의
    6. `start_server.bat` → http://127.0.0.1:5000 접속
    7. Focus 탭에서 기사/PDF 첨부 → 생성 → 미리보기 → 발간
- 의존: Step 1–4 의 산출물.

### Step 6. 시드 데이터 정리 (zip 패키징 직전)
- 대상 (zip 빌드 스크립트, 신규 `scripts/win/build_portable_zip.ps1`):
  - 본 repo 를 별도 디렉토리에 export → `data/db/*.csv` 를 헤더만 있는 빈 파일로 재생성 (`src/db.py:SHEET_HEADERS` 기준)
  - `data/manual_reports/`, `data/newsletters/`, `logs/` 비우기
  - `credentials/` 비우기
  - `.env` 제외 (`.env.example` 만)
  - `.git/`, `__pycache__/`, `.pytest_cache/`, `.venv/`(메인 운영자의) 제외
  - 옵션: `.venv-win/` 새로 생성하여 동봉 (Windows에서 직접 빌드 필요)
- 의존: 모든 Step. 빌드 산출물 zip 의 SHA-256 을 README 에 기재.

### Step 7. Claude Coworker / AI 운영 환경 이식 가이드 (별도 §7 참조)
- 대상 파일: `docs/AI_OPS_PORTING.md` (신규)
- 내용은 §7 그대로 옮겨 적음.
- 코드 변경 없음.

### Step 8. (선택) `MANUAL_REPORTS_DIR` 절대 경로화 검토
- 대상 파일: `src/manual_reports.py:29` (`MANUAL_REPORTS_DIR = Path("data") / "manual_reports"`)
- 현재는 **현재 작업 디렉토리 상대 경로** → `start_server.bat` 가 폴더에서 실행되면 OK. 그러나 작업 스케줄러로 호출 시 CWD 가 다르면 잘못된 위치에 저장될 수 있음.
- 변경 옵션:
  - (a) 그대로 두고 `run_daily.bat` 에 `cd /d %~dp0` 강제 (현재 이미 그렇게 되어 있음 — 안전)
  - (b) `Path(__file__).resolve().parent.parent / "data" / "manual_reports"` 로 절대화. 다른 호출자(예: pytest) 영향 검토 필요.
- 의존: Step 4. **이 Step 은 변경 비추천** (회귀 위험 vs 이득 작음). 문서로만 명시.

---

## 7. Claude Coworker / 다른 AI 운영 환경 이식 (별도 절)

### 7.1 전제 분리
**코드 배포(§3–6) 와 AI 운영 환경 이식은 별개.** 동료 PC 에 `newsletter-system` 코드가 도착해도, `.claude/agents/upgrade-planner.md` 등 **에이전트 정의 파일은 "도구"가 아니라 "프롬프트 스펙"** 일 뿐이다. 그것을 실제 실행하는 주체는 **별도의 AI 클라이언트**다.

### 7.2 가정과 대안 (Coworker 정의 모호성)
사용자는 "Cowork은 Claude Code 기반"으로 추정. 정의가 불명확하므로 세 가지 가정 분기를 둔다.

| 가정 | Coworker 의 실체 | `.claude/agents/*` 이식 가능성 |
|---|---|---|
| 가정-1 | Anthropic Claude Code CLI 의 사내 fork / 코워커 모드 | ★★★★★ — `agents/` 폴더 디렉토리 구조와 frontmatter 그대로 인식 가능 (Claude Code 의 sub-agent 스펙 그대로) |
| 가정-2 | Claude.ai 웹/데스크탑 + 프로젝트 기능 | ★★ — 폴더 단위 sub-agent 자동 위임은 미지원. `agents/*.md` 내용을 "프로젝트 지침" 또는 "커스텀 인스트럭션"으로 옮겨야 함. Bash 등 도구 권한 모델 다름 |
| 가정-3 | 사외 Coworker(미정) — Cursor / Aider / Goose 등 | ★ — 각 도구의 에이전트 모델·도구 권한 모델이 달라, **재작성 필요** |

### 7.3 `.claude/agents/*` 이식 매트릭스

| 항목 | Claude Code CLI (메인 가정) | Claude.ai 웹/Projects | Cursor | Aider | Goose | LLM 없이 (전통 README) |
|---|---|---|---|---|---|---|
| `upgrade-planner.md` (Read/Glob/Grep/Bash/WebFetch) | 그대로 | 도구 권한 모델 다름 — 사용자가 수동 첨부/요약 | "Rules for AI" 또는 `.cursor/rules` 로 이전 | 사용자 명령(`/architect`) 또는 read-only 모드 | "memory" / "instructions" 로 등록 | `docs/AI_OPS_PORTING.md` 의 절차 문구로 대체 |
| `code-modifier.md` (Edit/Write) | 그대로 | "캔버스" 또는 코드블록 복붙 | 자동 적용 + 사용자 승인 | 디폴트 동작 | 디폴트 동작 | `git apply patch` 로 사용자가 직접 |
| `integration-tester.md` (pytest 실행) | 그대로 | Bash 미지원 → 사용자가 수기 실행 후 결과 붙여넣기 | Cursor 의 terminal | Aider는 자체 pytest 통합 | shell exec 도구 | 사용자가 `pytest tests/ -v` 직접 |
| 메인 세션의 git push 정책 (CLAUDE.md) | 그대로 | 사용자가 수동 | 사용자가 수동 | Aider가 자동 commit (옵션) | 사용자가 수동 | 사용자가 수동 |

### 7.4 가장 단순한 비-AI 보조 경로 (낙폭 안전망)
**동료가 어떤 AI 보조 도구도 없이 운영해야 한다면**, 다음만 필요하다:
- `python main.py --mode server` 로 웹 UI 실행 후 Focus 탭에서 클릭 수준의 작업만 수행.
- 이 흐름은 LLM 자동화와 무관 — 모든 자동화는 **백엔드(`web_ui/app.py:/focus/publish`)** 안에 캡슐화되어 있음.
- 즉 `.claude/agents/*` 가 동료 PC 에 가지 않아도 운영은 100% 가능. 에이전트 정의는 **개발/업그레이드 작업** 때만 필요.

### 7.5 결론
- **운영(send newsletter): AI 보조 도구 불요.** 동료 PC 에 `.claude/agents/` 가 없어도 됨.
- **유지보수(코드 업그레이드): AI 보조 도구 필요.** 메인 운영자가 자기 PC 에서 수행 → 배포 zip 갱신. 동료에게 에이전트 정의를 강제로 옮기지 않는다.
- **만약 동료도 업그레이드 작업을 한다면**: 가정-1(Claude Code CLI) 전제로 `.claude/agents/` 그대로 복사 + `CLAUDE.md` 그대로 사용. 그 외 도구일 때는 §7.3 매트릭스에 따라 변환 필요 → 별도 과제.

---

## 8. 리스크 / 롤백 / 합격 조건

### 8.1 리스크 (영향도 × 발생가능성)
| 리스크 | 영향 | 가능성 | 완화 |
|---|---|---|---|
| OAuth 동의 화면 첫 통과 시 동료 PC 의 localhost 콜백 차단 | 발송 자체 불가 | 중 | `run_local_server(port=0)` → 고정 포트로 명시 + 방화벽 예외 가이드 |
| Anthropic API 키를 메인 PC 와 공용 → rate limit/감사 추적 어려움 | 운영 안정성 | 중 | 동료에게 별도 키 발급 권장. config 변경 없음 |
| `features.git_autosync: true` 가 동료 PC 에 잘못 켜진 채 배포 → publish 차단 | Focus/Weekly 발송 실패 | 중 | Step 1 의 기본값 강제. README 에 강조 |
| `recipients.focus` 키 미정의로 첫 Focus 발송 시 `ValueError` | 첫 사용 실패 | 높 | Step 1 에서 빈 리스트로라도 정의 + UI 측 friendly error |
| pdfplumber 의 native dep (pdfminer.six) Windows 휠 누락 | 보고서 PDF 첨부 실패 | 낮 | requirements.txt 핀 + Windows wheel 사전 빌드 zip 동봉 |
| Windows 작업 스케줄러가 절대 경로 하드코딩 (`task_schedule.xml`) | Daily 자동 실행 실패 | 높 | Step 4 의 템플릿화. 동료 시나리오에선 미사용 권장 |
| `data/db/*.csv` 의 레거시 헤더(`drive_doc_id, nlm_notebook`)와 코드 헤더 불일치 → DictWriter 키 누락 | 발송 이력 기록 실패 | 중 | Step 0. 동료 zip 은 새 헤더만 사용 |
| 동료가 메인 PC 의 `credentials/google_token.json` 을 복사해서 사용 | OAuth refresh 충돌, 토큰 회수 | 중 | README 에 명시적 금지 + Step 6 에서 zip 에 미포함 |
| Drive 차단이 향후 Gmail 차단으로 확장 | 발송 자체 불가 | 낮 | 본 시스템은 Gmail SMTP fallback 미구현. 별도 과제로 분기 |
| 사내 SSL inspection 프록시로 Anthropic API 차단/MITM | Claude 호출 실패 | 중 | requests 의 CA bundle override 가이드를 TROUBLESHOOTING.md 에 |

### 8.2 롤백 절차
| 단계 | 롤백 방법 |
|---|---|
| Step 1 (config 기본값) | git revert 또는 동료에게 이전 zip 재배포 |
| Step 3–4 (Windows 스크립트) | 신규 파일이므로 단순 삭제. 기존 `run_daily.bat`, `register_task.bat`, `task_schedule.xml` 은 보존되어 영향 없음 |
| Step 6 (zip 빌드) | zip 만 폐기. 메인 PC 코드는 영향 없음 |
| 전체 | 동료 PC 에서 `.venv` 삭제 + `data/` 백업 후 `git pull` 로 메인 PC 와 동기화 |

### 8.3 합격 조건 (`integration-tester` 가 점검)

코드 변경이 수반된 Step (1, 2, 3, 4, 6) 마무리 후, 다음을 측정 가능한 기준으로 확인한다.

#### 8.3.1 사전 정합성
- [ ] `python -m py_compile` 가 변경된 모든 .py 파일에서 통과.
- [ ] `python -m pytest tests/ -v` 전체 통과 (회귀 0).
- [ ] `git grep -nE "(drive|notebooklm)" -- ":!plan/*" ":!prd/*" ":!docs/*"` 결과에 새로운 활성 코드 경로 0건 (주석/문자열만 허용).

#### 8.3.2 동료 PC 시뮬레이션 (메인 운영자 PC 에서라도 재현 가능)
- [ ] zip 추출 → `setup_local.bat` 실행 시 60초 안에 OAuth 브라우저가 열리거나 명확한 에러 메시지가 표시된다.
- [ ] `start_server.bat` 더블클릭 후 30초 안에 `http://127.0.0.1:5000` 가 200 OK 를 반환한다.
- [ ] **Drive 도메인 차단 시뮬레이션**(예: hosts 로 `127.0.0.1 drive.google.com docs.google.com`) 상태에서 Focus 탭 발송이 **에러 없이** 완료된다.
- [ ] Focus 탭에서 (a) URL 기사 1건 추가, (b) PDF 파일 1건 업로드, (c) "발간" 클릭 후 **5분 이내** Gmail 발송 성공 응답.
- [ ] Gmail 의 Sent 폴더에 `build_email_subject("focus", date_str)` 와 일치하는 메일 1건이 존재.

#### 8.3.3 안전 가드
- [ ] `credentials/google_token.json`, `.env` 가 zip 산출물 어디에도 포함되지 않는다 (`unzip -l ... | grep -E "token|\\.env$"` 결과 0건).
- [ ] `config.yaml` 의 동료 변종에서 `features.git_autosync` 가 `false` 이고, `features.news_mode` 가 `"gnews"` 다.
- [ ] `recipients.focus` 키가 존재 (빈 리스트라도) — 미정의로 인한 KeyError 회귀 차단.

#### 8.3.4 AI 운영 환경 분리 검증 (문서만)
- [ ] `docs/AI_OPS_PORTING.md` 가 §7.3 매트릭스를 포함.
- [ ] `.claude/agents/*.md` 가 동료 zip 에 **포함되지 않거나**, 포함된 경우 README 에 "운영엔 불요, 업그레이드 작업 시만 필요" 가 명시.

---

## 9. 부록

### 9.1 동료 PC 사양 권장치
| 항목 | 권장 | 비고 |
|---|---|---|
| OS | Windows 10 22H2 또는 Windows 11 | UTF-8 코드페이지 활성화 권장(`chcp 65001`) |
| CPU/RAM | 4코어 / 8GB+ | Focus 흐름은 가벼움. A' 미사용 시 더 가벼움 |
| 디스크 | 빈 공간 2GB+ | zip 추출 후 ~300MB, PDF 첨부 누적 |
| Python | 3.11.x (동봉 사용 가능) | `pdfplumber` 휠 호환 |
| 네트워크 | Anthropic, Google(Gmail) 접근 가능, **`mail.google.com` HTTPS 통과 필수** | Drive 차단은 무관 |
| 브라우저 | Chrome/Edge 최신 (OAuth 동의용) | Internet Explorer 비호환 |

### 9.2 보안 고려
- API 키 보관: `.env` 는 디스크 평문 — 사내 권장은 Windows Credential Manager 또는 사내 시크릿 매니저. 본 시스템은 단계 1 으로 `.env` 사용, 추후 별도 과제로 이전 가능.
- OAuth scope 최소화: `gmail.send` + `gmail.readonly` 2개만. Drive scope 0개. (§2.1)
- 토큰 격리: `credentials/google_token.json` 은 PC 단위로 생성. 메인 PC 토큰 복사 금지.
- 로그 마스킹: `logs/spri.log` 에 이메일 본문/HTML 풀바디 미기록(현 코드 확인됨). `git_sync` 가 push 할 때 시크릿 미포함(`data/newsletters/`, `data/db/` 만 add).
- PDF 업로드 SSRF 방어: `src/manual_reports.py:is_safe_url` 가 private/loopback IP 차단 — 사내망 URL 직링크 첨부 시 차단되는 점 주지 (FAQ 에 추가).

### 9.3 사내 정책 / 라이선스 체크리스트
- [ ] Anthropic 상용 이용 약관 검토 (사내 데이터를 모델 학습에 사용하지 않음 확인)
- [ ] Google Cloud OAuth Client 가 사내 SPRi 도메인 소유 프로젝트로 발급되었는지
- [ ] Python 3.11 (PSF 라이선스), Flask (BSD), pdfplumber (MIT), anthropic SDK (MIT), google-api-python-client (Apache 2.0) — 사내 OSS 정책 통과 확인
- [ ] 동료 PC 에 Python 설치 권한 (또는 embeddable Python 사용 허가)
- [ ] 메일 발송 발신자 계정의 사내 정책(공용 계정 / 개인 계정 / 위임발송 한도)
- [ ] (선택) git push 대상 사내 호스팅의 LFS 한도 / 푸시 빈도 정책

### 9.4 변경 후 동료에게 전달할 자료 목록
- [ ] `spri-newsletter-v<date>.zip` (Step 6 산출물)
- [ ] zip 의 SHA-256
- [ ] OAuth client JSON (별도 채널)
- [ ] 동료가 발급해야 할 키 목록 (Anthropic, GNews(선택))
- [ ] DEPLOY_WINDOWS.md 인쇄본 또는 사내 위키 링크
- [ ] 메인 운영자 비상 연락처

---

## 10. 후속 흐름 안내

사용자가 본 기획서의 **추천 안 B(Portable zip)** 에 동의하면, 다음 단계는 `code-modifier` 에 본 문서 §6 의 Step 0–6 (필요 시 Step 7–8) 을 그대로 전달하여 코드/스크립트 변경을 진행하고, 그 직후 `integration-tester` 에 §8.3 합격 조건을 넘겨 PASS 여부를 판정받은 뒤, 메인 세션이 사용자 명시 지시 하에 커밋·푸시한다.
