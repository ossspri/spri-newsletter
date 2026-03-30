# SPRi Newsletter System - Implementation Plan

## Context
SPRi(소프트웨어정책연구소)의 글로벌 SW 산업 동향 뉴스레터 자동화 시스템을 Google Apps Script에서 로컬 Python으로 마이그레이션한다. 기존 코드(`reference/`)의 동작을 보존하면서 PRD v1.0의 확장 요구사항(NotebookLM, Web UI, Weekly 보고서)을 구현한다. Claude Code의 Skill과 MCP 도구를 최대한 활용하여 개발 효율을 높인다.

---

## Phase 1: 프로젝트 스캐폴딩 + DB + 유틸리티

**목표**: 프로젝트 골격, 설정 로딩, SQLite 4테이블, 공통 유틸리티

**생성 파일**:
- `main.py` — CLI 진입점 (`--mode daily|server|fetch-only`), config/env 로딩, 로깅 초기화
- `config.yaml` — PRD 6.4 구조 그대로
- `.env.example` — 플레이스홀더 키
- `.gitignore` — `.env`, `credentials/google_token.json`, `data/`, `logs/`, `__pycache__/`
- `requirements.txt` — PRD 12절 의존성
- `src/__init__.py`
- `src/db.py` — `init_db()`, `insert_daily_articles()`, `get_existing_summaries()`, `check_today_sent()`, `log_newsletter()`, `archive_articles()` 등
- `src/utils.py` — KST 날짜 헬퍼, `@retry(max_retries, delay)` 데코레이터, 마크다운→HTML 변환기
- 디렉토리: `data/`, `data/newsletters/`, `credentials/`, `logs/`, `web_ui/`, `web_ui/templates/`, `web_ui/static/`

**핵심 구현**:
- SQLite 스키마: PRD 6.3 그대로 (`daily_articles`, `manual_articles`, `article_archive`, `newsletter_log`)
- 마크다운→HTML 변환: `reference/runDailyAutomation.js:209-216` 정규식 체인 보존, 색상만 PRD 5.2로 변경 (`#1a2a3a`, `#2d5a8e`)

**TDD**: `tests/test_db.py`, `tests/test_utils.py` 먼저 작성
**검증**: `python main.py --mode fetch-only` 실행 시 DB 생성 후 정상 종료
**Skill/도구**: 없음 (순수 인프라)

---

## Phase 2: 뉴스 수집 서비스 (GNews API)

**목표**: GNews API 연동, 6개 쿼리 수집, 중복제거, 25건 제한

**생성 파일**:
- `src/news_service.py` — `GNewsService`: `fetch_articles()`, `_query_gnews(keyword)`, `_dedup_articles()`, `_sort_and_limit(max=25)`

**핵심 구현**:
- 6개 쿼리: PRD 3.1.1 (`"software industry AI"` 등)
- `https://gnews.io/api/v4/search` + `lang=en`, `from=24h_ago(UTC)`, `max=50`
- `@retry(max_retries=2, delay=10)` 적용
- URL 기준 중복제거 → `publishedAt` 내림차순 정렬 → 25건 제한 → SQLite 저장

**TDD**: `tests/test_news_service.py` (모킹된 HTTP 응답으로 dedup/sort/limit 검증)
**검증**: `python main.py --mode fetch-only`로 실제 수집 확인

**Skill/도구**:
- `WebFetch` — GNews API 현재 응답 형식 검증

---

## Phase 3: Claude API 보고서 생성

**목표**: Anthropic SDK로 SPRi 양식 보고서 생성

**생성 파일**:
- `src/prompts.py` — Daily/Weekly 프롬프트 템플릿 (`reference/runDailyAutomation.js:47-106` 마이그레이션)
- `src/claude_service.py` — `ClaudeService`: `generate_daily_report(articles, summaries)`, `generate_weekly_report()`, `_call_claude(prompt)`, `_postprocess(text)`

**핵심 구현**:
- `anthropic` Python SDK 사용 (system 파라미터 분리)
- 모델: `claude-sonnet-4-20250514`, `max_tokens: 4096`
- `@retry(max_retries=3, delay=30)` 적용
- 후처리: `reference/:140-155` 전처리 텍스트 제거 로직 보존
- 실패 시 `None` 반환 → `main.py`에서 기사목록만 발송 (PRD 10절)

**보존 필수**:
- 6섹션 한국어 헤더: `## 1. 개요` ~ `## 6. 하드웨어/인프라`
- `**볼드 요약**`, `* [기사 제목](URL)` 형식
- `<provided_articles>` 블록으로 기사 전달 (PRD 3.3.1)

**TDD**: `tests/test_prompts.py`, `tests/test_claude_service.py`

**Skill/도구**:
- **`claude-api` Skill** — `claude_service.py` 구현 시 호출하여 Anthropic SDK best practice 적용
- **`simplify` Skill** — 모듈 완성 후 코드 품질 리뷰

---

## Phase 4: 이메일 템플릿 + Gmail 발송

**목표**: SPRi 브랜딩 HTML 이메일 + Gmail API OAuth2 발송

**생성 파일**:
- `src/email_template.py` — `render_newsletter_email(markdown, date_str, doc_url, type)`
- `src/gmail_service.py` — `GmailService`: `authenticate()`, `send_newsletter(html, recipients, subject)`

**핵심 구현 (email_template.py)**:
- PRD 5.2 구조: 그라디언트 헤더(`#1a2a3a`→`#2d5a8e`), "소프트웨어정책연구소", 날짜, 본문, 푸터
- `reference/runDailyAutomation.js:208-235` HTML 구조 보존 + PRD 색상 업데이트
- 폴백 템플릿: Claude 실패 시 기사목록만 포함

**핵심 구현 (gmail_service.py)**:
- `google-auth-oauthlib` `InstalledAppFlow`, 토큰 자동갱신
- `MIMEText(html, 'html')`, base64url 인코딩
- 제목: `[Daily] 글로벌 SW산업동향 (YYYY-MM-DD)`

**TDD**: `tests/test_email_template.py`, `tests/test_gmail_service.py`

**Skill/도구**:
- **Gmail MCP `gmail_get_profile`** — OAuth 연결 상태 확인
- **Gmail MCP `gmail_create_draft`** — 테스트 이메일 초안 생성하여 렌더링 시각 검증
- **Gmail MCP `gmail_list_labels`** — 라벨 구성 확인
- **`simplify` Skill** — 코드 리뷰

---

## Phase 5: Google Drive 저장 + NotebookLM 아카이브

**목표**: 구글 문서 저장, NotebookLM 원천자료 아카이브

**생성 파일**:
- `src/drive_service.py` — `DriveService`: `save_as_google_doc(markdown, title, folder_id)`
- `src/notebooklm_service.py` — `NotebookLMService`: `get_or_create_weekly_notebook(date)`, `add_article_sources()`, `add_newsletter_text()`

**핵심 구현**:
- Drive: Google Docs API batch update로 스타일링 (`reference/:159-205` 참조)
- 명명: `SPRi_일간브리핑_YYYY-MM-DD` / `SPRi_주간동향_YYYY-MM-DD`
- NotebookLM: 주간 노트북 `SPRi_{연도}_{월요일날짜}`, 기사 URL 건별 소스 추가
- NotebookLM 실패 시 파이프라인 계속 진행 (비핵심, PRD 10절)

**TDD**: `tests/test_drive_service.py`, `tests/test_notebooklm_service.py`

**Skill/도구**:
- **`WebFetch`** — `notebooklm-py` GitHub 리포 README 확인하여 실제 API 시그니처 검증
- **`simplify` Skill** — 코드 리뷰

---

## Phase 6: 웹 UI (Flask — Daily + Weekly 탭)

**목표**: 전문가용 로컬 웹 UI 구현

**생성 파일**:
- `web_ui/__init__.py`
- `web_ui/app.py` — Flask 라우트:
  - `GET /daily` — 오늘 수집 기사 + 발송 상태
  - `POST /daily/fetch`, `/daily/generate`, `/daily/send`, `/daily/save-drive`
  - `GET /weekly` — 7일간 기사 체크박스 선택
  - `POST /weekly/add-article`, `/weekly/generate`, `/weekly/send`, `/weekly/save-drive`
- `web_ui/templates/base.html` — 탭 네비게이션 레이아웃
- `web_ui/templates/daily.html` — 수집→생성→미리보기→발송 3단계
- `web_ui/templates/weekly.html` — 기사선택(`N/25`)→생성→발송
- `web_ui/static/style.css`

**핵심 구현**:
- 미리보기: `email_template.py` 렌더링 결과를 iframe으로 표시
- "오늘 발송 완료" 배지: `newsletter_log` 조회
- Weekly 기사 목록: 날짜별 그룹핑, 25건 제한 경고
- 수동 기사 추가: `beautifulsoup4`로 URL 메타 추출
- AJAX + 로딩 스피너 (Claude 생성 등 장시간 작업)

**TDD**: `tests/test_web_ui.py` (Flask test client)
**검증**: `http://localhost:5000`에서 Daily/Weekly 전체 사이클 수행

**Skill/도구**:
- **Gmail MCP `gmail_create_draft`** — UI에서 발송 전 초안 테스트
- **`simplify` Skill** — 코드 리뷰

---

## Phase 7: 파이프라인 통합 + 스케줄링 + 운영

**목표**: 전체 파이프라인 연결, 크론/스케줄 설정, 에러 처리 완성

**생성/수정 파일**:
- `main.py` — `run_daily_pipeline()` 11단계 완성 (PRD 7.2)
- `setup_cron.sh` — PRD 7.3 크론 등록 헬퍼

**파이프라인 11단계**:
1. config.yaml + .env 로드
2. GNews 6개 쿼리 수집
3. 중복제거 + 25건 + SQLite 저장
4. 기존 요약 조회 (중복배제용)
5. Claude API → 마크다운 생성
6. 마크다운 → HTML 변환
7. Gmail 발송 (Daily 수신자)
8. Google Drive 문서 생성
9. NotebookLM 소스 저장
10. SQLite 발송이력 기록
11. 로컬 `.md` 백업

**에러 처리** (PRD 10절):
| 상황 | 처리 |
|------|------|
| GNews 실패 (2회) | 에러 알림 이메일, 중단 |
| Claude 실패 (3회) | 기사목록만 발송 |
| 기사 0건 | "해당 기간 주요 신규 동향 없음" 발송 |
| Gmail 실패 | `newsletter_log`에 failed 기록 |
| Drive/NLM 실패 | 로그 기록, 계속 진행 |

**TDD**: `tests/test_pipeline.py` (각 실패 모드 주입 테스트)

**Skill/도구**:
- **`schedule` Skill** — Daily 파이프라인 원격 에이전트 스케줄 설정 (OS 크론 보조)
- **`loop` Skill** — 테스트 중 `logs/spri.log` 모니터링
- **Gmail MCP `gmail_search_messages`** — 발송 완료 후 수신 확인
- **`simplify` Skill** — 전체 코드 최종 리뷰

---

## Phase 의존성 그래프

```
Phase 1 (스캐폴딩+DB+유틸)
  |
  +---> Phase 2 (GNews) --------+
  +---> Phase 3 (Claude) -------+---> Phase 7 (통합)
  +---> Phase 4 (Email+Gmail) --+
  +---> Phase 5 (Drive+NLM) ----+
  |
  +---> Phase 6 (Web UI) — Phase 2~5 완료 후
```

Phase 2~5는 Phase 1 완료 후 **병렬 개발 가능**. Phase 6은 모든 서비스 모듈 필요. Phase 7은 전체 통합.

---

## Skill/도구 활용 요약

| Skill/도구 | Phase | 용도 |
|-----------|-------|------|
| `claude-api` | 3 | Anthropic SDK 코드 생성 best practice |
| `simplify` | 3,4,5,6,7 | 각 Phase 완성 후 코드 품질 리뷰 |
| Gmail `gmail_get_profile` | 4 | OAuth 연결 확인 |
| Gmail `gmail_create_draft` | 4,6 | 이메일 렌더링 시각 검증 |
| Gmail `gmail_search_messages` | 7 | 발송 완료 확인 |
| Gmail `gmail_list_labels` | 4 | 라벨 구성 확인 |
| `WebFetch` | 2,5 | GNews API / notebooklm-py API 검증 |
| `schedule` | 7 | Daily 자동 실행 스케줄 설정 |
| `loop` | 7 | 파이프라인 테스트 모니터링 |

---

## 참조 파일

| 파일 | 용도 |
|------|------|
| `prd/SPRi_Newsletter_System_PRD_v1.0.md` | 전체 요구사항 명세 |
| `reference/runDailyAutomation.js` | 프롬프트(47-106), HTML 템플릿(208-235), Docs 스타일(159-205), MD→HTML 변환(209-216), 재시도(245-256) |
| `reference/config.js` | 기존 모델/API 설정 (GPT→Claude 변경) |
| `reference/recipients.js` | 수신자 관리 패턴 |

---

## 검증 체크리스트 (E2E)

1. `python main.py --mode fetch-only` — 기사 수집 + SQLite 저장
2. `python main.py --mode daily` — 전체 11단계 파이프라인 성공
3. Gmail 수신 확인 — SPRi 브랜딩 정상 렌더링
4. Google Drive — 지정 폴더에 구글 문서 생성
5. NotebookLM — 주간 노트북에 기사 소스 추가
6. `python main.py --mode server` — 웹 UI Daily/Weekly 전체 사이클
7. `schedule` 스킬 — 스케줄된 자동 실행 확인
