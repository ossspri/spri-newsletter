# SPRi 뉴스레터 자동화 시스템 PRD

> **Product Requirements Document**
> 문서 버전: 1.1 | 작성일: 2026-03-29 | 갱신일: 2026-04-08 | 상태: Released

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|-----------|
| 1.0 | 2026-03-29 | 초기 PRD 작성 (Draft) |
| 1.1 | 2026-04-08 | 구현 결과 반영 — DB를 SQLite에서 Google Sheets로 변경, NotebookLM 인증 방식 변경(Playwright 기반), NotebookLM 저장 범위를 Weekly만으로 축소, GNews 쿼리 재구성(10개·섹션별 분류), Claude max_tokens 16,000으로 증가, Web UI 기능 대폭 추가(키워드 편집·미리보기·번역·재인증·초기화·통합 발행), 스케줄 시간 KST 05:00으로 조정, Windows Task Scheduler 지원 강화 |

---

## 1. 개요

### 1.1 프로덕트 요약

소프트웨어정책연구소(SPRi)의 글로벌 SW 산업 동향 뉴스레터를 자동으로 수집·생성·배포하는 **로컬 실행 시스템**.
Daily와 Weekly 두 가지 주기로 운영하며, 로컬 머신에서 Python으로 동작한다.
Daily는 OS 스케줄러 자동 실행과 전문가 수동 실행을 모두 지원하고, Weekly는 전문가가 UI에서 기사를 선별하여 생성한다.
원천 자료는 notebooklm-py를 통해 Google NotebookLM에 저장하고(Weekly만 해당), 보고서는 Google Drive에 구글 문서로 저장한다.

### 1.2 배경 및 목적

- SPRi 산업분석팀이 수작업으로 수행하던 뉴스 큐레이션·보고서 작성·배포 업무를 자동화
- 매일 일관된 품질의 산업 동향 브리핑을 정시 발송하되, PC가 꺼져 있을 때는 전문가가 수동으로도 실행 가능
- 전문가는 주간 보고서의 기사 선별과 최종 검토에만 집중
- NotebookLM을 주간 기사 아카이브 및 분석 허브로 활용

### 1.3 기술 스택

| 항목 | 선택 | 근거 |
|------|------|------|
| 런타임 | Python 3.11+ (로컬) | 로컬 실행, 풍부한 라이브러리 생태계 |
| 스케줄러 | OS 네이티브 (macOS/Linux: `crontab`, Windows: 작업 스케줄러) | 외부 서비스 의존 없이 정시 자동 실행 |
| 뉴스 수집 | GNews API (gnews.io) | REST API, 시간 필터링 지원, 무료 티어 제공 |
| AI 생성 | Anthropic Claude API (`claude-sonnet-4-20250514`) | 한국어 고품질 보고서 생성, 프롬프트 제어 용이 |
| 이메일 발송 | Gmail API (google-api-python-client) | OAuth2 인증, HTML 메일 지원 |
| 보고서 저장 | Google Drive API (google-api-python-client) | 구글 문서 자동 생성 |
| 원천 자료 저장 | notebooklm-py (https://github.com/teng-lin/notebooklm-py) | NotebookLM에 기사 URL 건별 저장, 주간 노트북 관리 |
| 데이터 관리 | Google Sheets (gspread) | 기사 아카이브, 발송 이력을 클라우드 스프레드시트로 관리 |
| Web UI | Flask (로컬 웹앱) | 전문가가 브라우저에서 Daily 수동 실행 및 Weekly 기사 선별·발송 지시 |
| 설정 관리 | `.env` 파일 + `config.yaml` | API 키는 환경변수, 운영 설정은 YAML |

---

## 2. 사용자 및 역할

| 역할 | 설명 | 주요 행동 |
|------|------|-----------|
| 시스템 (자동) | OS 스케줄러로 Daily 파이프라인 실행 | 뉴스 수집 → 보고서 생성 → 이메일 발송 → Drive 저장 → Google Sheets 기록 |
| 전문가 (수동) | SPRi 산업분석 담당자 | Daily 수동 실행 (스케줄러 미작동 시), Weekly 기사 선별, 보고서 검토/수정, 발송 지시 |
| 수신자 | 뉴스레터 구독자 | 이메일 수신 (Daily/Weekly 그룹 분리) |

---

## 3. 기능 요구사항

### 3.1 뉴스 기사 수집

#### 3.1.1 자동 수집 (Daily)

- **API**: GNews API (`https://gnews.io/api/v4/search`)
- **검색 키워드** (10개 쿼리를 순차 호출, 섹션별 분류):
  - 기업/산업: `artificial intelligence`, `big tech AI`, `software industry`, `SaaS`
  - 정책/법제: `AI regulation`, `AI policy`
  - 인력/교육: `software developer AI`
  - 기술/연구: `AI model`
  - 하드웨어/인프라: `AI semiconductor`, `AI datacenter`
- **필터 조건**:
  - `from`: 현재 시각 기준 24시간 이전 (ISO 8601)
  - `lang`: `en`
  - `max`: 쿼리당 25건
- **후처리**:
  - URL 기준 중복 제거
  - 발행일 기준 최신순 정렬
  - 최대 25건으로 제한
- **저장**: 수집 결과를 Google Sheets `daily_articles` 시트에 기록

#### 3.1.2 수동 수집 (Weekly 보완용)

- 전문가가 Web UI에서 기사 URL을 직접 입력
- 시스템이 URL에서 제목·요약을 자동 추출 (BeautifulSoup og:title/og:description)하여 Google Sheets에 저장

### 3.2 뉴스레터 생성

#### 3.2.1 Daily 뉴스레터

- **트리거 (이중 방식)**:
  - **자동**: OS 스케줄러 (Windows 작업 스케줄러 / Linux crontab) — PC가 켜져 있을 때 정시 실행
  - **수동**: 전문가가 Web UI에서 "뉴스레터 생성" 버튼 클릭 — PC가 꺼져 있었거나 스케줄러가 실패했을 때 수시 실행
- **실행 명령 (자동)**: `python main.py --mode daily`
- **중복 방지**: 같은 날 이미 Daily가 발송된 경우, 수동 실행 시 "오늘 이미 발송됨" 경고를 표시하고 전문가가 재발송 여부를 선택
- **입력**: 자동 수집된 기사 목록 (최대 25건)
- **처리**: Claude API 호출하여 SPRi 양식 보고서 생성
- **출력**: 마크다운 형식의 뉴스레터 본문

#### 3.2.2 Weekly 보고서

- **트리거**: 전문가가 Web UI에서 "생성" 버튼 클릭
- **입력**: 전문가가 한 주간 Daily 기사 목록에서 선택한 기사 (최대 25건)
- **처리**: Claude API 호출하여 주간 심층 분석 보고서 생성
- **출력**: 마크다운 형식의 주간 보고서 본문

#### 3.2.3 보고서 섹션 구조 (Daily/Weekly 공통)

```
## 1. 개요 (Key Messages)
   - 가장 중요한 3~5가지 뉴스 요약 및 인사이트

## 2. 정책/법제
   - 글로벌 규제, 표준화, 정부 정책 동향

## 3. 기업/산업
   - 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
   - GICS 코드 기반 분류 적용

## 4. 인력/교육
   - 개발자 직무 변화, 신기술 교육, 고용 트렌드

## 5. 기술/연구
   - 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신

## 6. 하드웨어/인프라
   - AI 반도체(GPU/NPU/HBM), 데이터센터, 에너지(전력/원전/SMR)
```

#### 3.2.4 보고서 작성 규칙

| 규칙 | 상세 |
|------|------|
| 기사 수 상한 | 뉴스레터당 25건 이하 |
| 상세도 | 각 동향 항목은 3문장 이상으로 구체적·전문적으로 기술 |
| 문체 | 전문적 개조식 (~임, ~함), SPRi 리포트 톤 |
| 볼드 요약 | 각 동향 항목 첫 줄은 `**한 줄 요약**` 형식 |
| 출처 형식 | `* [기사 제목](기사 직접 URL)` — 본문 인라인 배치 (각주 방식 금지) |
| 허용 마크다운 | `## 섹션명`, `**볼드**`, `* [제목](URL)` 만 허용 |
| 언어 | 한국어 |
| 중복 배제 | 이전 뉴스레터에 포함된 동향과 중복되는 내용 제외 |
| 제외 대상 | 일반적 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례 |

#### 3.2.5 기사 선별 우선순위

1. AI·자동화가 기존 SW 산업(개발, 유통, 운영, 비즈니스 모델 등)에 끼치는 구체적 영향
2. AI 관련 정책·규제·표준이 SW 기업에 미치는 실질적 영향
3. AI 기술 자체의 연구·발표 (SW 산업 파급효과가 명확한 경우에 한해)

### 3.3 Claude API 프롬프트

#### 3.3.1 Daily 프롬프트 템플릿

```
<role>
당신은 소프트웨어정책연구소(SPRi)의 산업분석 에이전트입니다.
</role>
<main_task>
아래 제공된 기사 목록을 기반으로 글로벌 SW 산업 동향 리포트를 작성하십시오.

<provided_articles>
${articleList}
</provided_articles>

<sub_task> 리포트 작성
1. 구성: 다음 6개 섹션을 반드시 포함할 것.
  - ## 1. 개요 : 가장 중요한 3가지 뉴스 요약 및 인사이트
  - ## 2. 정책/법제: 글로벌 규제, 표준화, 정부 정책 동향
  - ## 3. 기업/산업: 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
  - ## 4. 인력/교육: 개발자 직무 변화, 신기술 교육, 고용 트렌드
  - ## 5. 기술/연구: 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신
  - ## 6. 하드웨어/인프라: AI 반도체(GPU/NPU/HBM), 데이터센터 아키텍처, 에너지
2. 상세도: 각 섹션 내 개별 동향 요약은 반드시 3문장 이상으로 구체적이고 전문적으로 기술할 것.
3. 스타일: 전문적인 개조식(~임, ~함), SPRi 리포트 톤 유지.
4. 각 동향 항목 첫 줄은 반드시 '**한 줄 요약 문장**' 형식의 볼드 요약으로 시작할 것.
5. 출처: 각 기사 하단에 '* [기사 제목](기사 직접 URL)' 형식으로 기재할 것.
6. 언어: 한국어.
7. 허용 마크다운: '## 섹션명', '**볼드**', '* [제목](URL)' 형식만 사용할 것.
</sub_task>
</main_task>
<constraints>
1. 제공된 기사 목록에서만 선별하여 사용할 것.
2. 기존 동향과 중복되는 내용은 제외할 것: ${existingSummaries}
3. 일반적인 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례 제외.
4. 리포트 본문만 출력할 것. 부가적 안내문구 금지.
5. 기사는 최대 25개까지만 포함할 것.
</constraints>
```

#### 3.3.2 Weekly 프롬프트 템플릿

Daily 프롬프트와 동일한 구조이되, 다음을 변경:
- `<role>` 내 "주간 분석" 명시
- 개요 섹션: "금주 가장 중요한 3~5가지 핵심 트렌드 요약 및 시사점"
- 상세도: "한 주간의 흐름과 맥락을 연결하여 심층 분석"

#### 3.3.3 기사 번역 프롬프트 (Weekly)

- Weekly 기사 선별 시 영문 기사의 제목·요약을 한국어로 번역
- Claude API를 통해 일괄 번역 수행
- 전문가의 기사 내용 이해를 돕기 위한 보조 기능

---

## 4. 산출물 저장

### 4.1 보고서 저장 (Google Drive)

| 항목 | 상세 |
|------|------|
| 형식 | 구글 문서 (Google Docs) |
| 위치 | Google Drive 내 지정 폴더 (`config.yaml`의 `drive.folder_id`) |
| 명명 규칙 | `SPRi_일간브리핑_YYYY-MM-DD` / `SPRi_주간동향_YYYY-MM-DD` |
| 구현 | Google Drive API (`googleapiclient`) 로 구글 문서 생성 후 폴더 이동 |
| 스타일링 | Google Docs API로 제목(파랑 #1a73e8, 볼드, 중앙), 부제(회색 #70757a), 헤더(HEADING_2, 배경 #f1f3f4) 등 전문적 서식 적용 |

### 4.2 원천 자료 저장 (NotebookLM) — Weekly만 해당

| 항목 | 상세 |
|------|------|
| 라이브러리 | `notebooklm-py` (https://github.com/teng-lin/notebooklm-py) |
| 저장 단위 | 뉴스레터에 인용된 기사의 URL 건별 |
| 노트북 구조 | 주 단위로 노트북 생성 (예: `SPRi_2026_0330`) |
| 저장 흐름 | Weekly 발행 시 → 인용된 기사 URL을 해당 주간 노트북에 소스로 추가 |
| 중복 방지 | 동일 URL 소스 중복 추가 방지 |
| 적용 범위 | **Weekly 발행 시에만** 저장 (Daily에서는 NotebookLM 저장을 수행하지 않음) |

#### 4.2.1 NotebookLM 연동 상세

```python
# notebooklm-py 사용 흐름 (의사코드)

# 1. 인증: Playwright 브라우저 자동화 + storage_state.json (쿠키 기반)
from notebooklm import NotebookLMClient
client = NotebookLMClient(storage_state="credentials/storage_state.json")

# 2. 주간 노트북 확인 또는 생성
week_label = "SPRi_2026_0330"  # 해당 주의 월요일 날짜 (MMDD)
notebook = await client.get_or_create_notebook(title=week_label)

# 3. 기사 URL을 소스로 추가 (건별, 중복 방지)
for article in newsletter_articles:
    await notebook.add_source(url=article["url"])

# 4. 뉴스레터 본문도 텍스트 소스로 추가
await notebook.add_source(text=newsletter_markdown)
```

#### 4.2.2 NotebookLM 노트북 명명 규칙

| 주기 | 노트북 제목 형식 | 예시 |
|------|----------------|------|
| 주간 | `{prefix}_{연도}_{해당 주의 월요일 MMDD}` | `SPRi_2026_0330` |

하나의 주간 노트북에 해당 주의 Weekly 기사 URL과 뉴스레터 본문이 저장된다.

#### 4.2.3 NotebookLM 인증

| 항목 | 상세 |
|------|------|
| 인증 방식 | Playwright 브라우저 자동화를 통한 쿠키 기반 인증 |
| 상태 파일 | `credentials/storage_state.json` (Playwright 저장) |
| 만료 감지 | 쿠키 만료 시간을 확인하여 Web UI에 인증 상태 배지 표시 |
| 재인증 | Web UI에서 "재인증 열기" → Playwright 브라우저 팝업 → Google 로그인 → "재인증 저장" |
| 스레드 관리 | Playwright 브라우저는 별도 스레드에서 실행 (Flask 메인 스레드와 분리) |

### 4.3 데이터 관리 (Google Sheets)

원천 자료의 주 저장소는 NotebookLM이지만, Google Sheets에 메타데이터를 보관하여 중복 검사 및 Weekly 기사 선별 UI에 활용한다.

#### 4.3.1 Google Sheets 스키마

```
시트 1: daily_articles (수집된 기사)
  id, collected_at, title, url, description, source_name, published_at, used_in

시트 2: manual_articles (수동 입력 기사)
  id, added_at, title, url, description, added_by

시트 3: article_archive (뉴스레터 인용 아카이브)
  id, newsletter_date, type, section, article_title, article_url, nlm_notebook_id

시트 4: newsletter_log (발송 이력)
  id, sent_at, type, article_count, recipient_count, status, error_message, drive_doc_id, nlm_notebook
```

- URL 기준 중복 방지 (`daily_articles`, `manual_articles`)
- Auto-increment ID 관리
- Google Sheets API 429 Rate Limit 대응 (지수 백오프 재시도)

### 4.4 로컬 백업

- Weekly 뉴스레터는 `data/newsletters/` 디렉토리에 마크다운 파일로 로컬 백업
- 파일명: `weekly_YYYY-MM-DD.md`

---

## 5. 이메일 배포

### 5.1 발송 방식

| 구분 | Daily | Weekly |
|------|-------|--------|
| 트리거 | OS 스케줄러 자동 실행 **또는** 전문가가 Web UI에서 수동 실행 | 전문가가 Web UI에서 "발행" 클릭 |
| 수신자 | `config.yaml`의 `recipients.daily` | `config.yaml`의 `recipients.weekly` |
| 구현 | Gmail API (`googleapiclient`) + OAuth2 | 동일 |
| 형식 | HTML 이메일 (SPRi 브랜딩 헤더/푸터 포함) |

### 5.2 이메일 템플릿 구조

```
구조:
├── 헤더 (그라디언트 배경 #1a2a3a → #2d5a8e)
│   ├── 기관명: "소프트웨어정책연구소" (11px, 대문자, letter-spacing: 3px)
│   ├── 제목: "Daily SW 산업 동향 브리핑" 또는 "주간 SW 산업 동향 보고서" (22px, bold)
│   └── 날짜: YYYY년 M월 D일 요일 (13px)
├── 본문 (흰색 배경, padding: 28px 32px)
│   └── 마크다운 → HTML 변환 결과
│       ├── ## → <h2> (color: #1a2a3a, border-bottom: 2px solid #2d5a8e)
│       ├── ** ** → <strong>
│       └── * [title](url) → 📎 <a> 링크 (color: #2d5a8e)
├── Drive 문서 링크 버튼 (있는 경우)
└── 푸터 (회색 배경, 11px, 중앙 정렬)
    └── "SPRi 소프트웨어정책연구소 | 본 뉴스레터는 AI 기반으로 자동 생성되었습니다"
```

- 폰트: Apple SD Gothic Neo, Malgun Gothic
- 반응형: max-width 700px

### 5.3 수신자 관리

- `config.yaml` 파일에서 관리
- Daily와 Weekly 수신자를 별도 키로 구분
- 파일 수정 즉시 반영 (다음 실행부터 적용)

---

## 6. 시스템 아키텍처

### 6.1 전체 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                     로컬 머신 (Python)                               │
│                                                                     │
│  ┌──────────┐    ┌───────────────┐    ┌──────────────┐             │
│  │ OS       │───▶│ main.py       │───▶│ GNews API    │             │
│  │ 스케줄러  │    │ --mode daily  │    │ 뉴스 수집     │             │
│  └──────────┘    └───────────────┘    └──────┬───────┘             │
│        ▲                                      │                      │
│        │ 자동 (PC 켜져 있을 때)                  │                      │
│        │                                      │                      │
│        │         ┌────────────────────────────┘                      │
│        │         ▼                                                   │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │                 Claude API 호출                             │     │
│  │         SPRi 6대 섹션 마크다운 보고서 생성                    │     │
│  └─────┬──────────┬──────────────┬──────────────┬────────────┘     │
│        │          │              │              │                    │
│        ▼          ▼              ▼              ▼                    │
│  ┌─────────┐ ┌─────────┐ ┌───────────┐ ┌──────────────┐           │
│  │ Gmail   │ │ Google  │ │ Google    │ │ Notebook     │           │
│  │ API     │ │ Drive   │ │ Sheets    │ │ LM           │           │
│  │ 발송    │ │ API     │ │ (gspread) │ │ (Weekly만)   │           │
│  │         │ │ 문서저장 │ │ 데이터관리 │ │ URL저장      │           │
│  └─────────┘ └─────────┘ └───────────┘ └──────────────┘           │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │              로컬 웹 UI (Flask) — Daily + Weekly 통합       │     │
│  │  http://localhost:5000                                     │     │
│  │                                                            │     │
│  │  [Daily 탭]                        [Weekly 탭]             │     │
│  │  • 키워드 미리보기/편집            • 주간 기사 목록 (체크박스) │     │
│  │  • 기사 미리보기 (저장 전 확인)    • 기사 한국어 번역          │     │
│  │  • 뉴스레터 생성 + 편집           • 수동 기사 추가            │     │
│  │  • 통합 발행 (이메일+Drive)        • 통합 발행 (이메일+Drive   │     │
│  │  • 오늘 발송 이력 표시               +NotebookLM+로컬백업)    │     │
│  │  • 초기화(Reset) 기능             • 초기화(Reset) 기능        │     │
│  │                                                            │     │
│  │  [공통] NotebookLM 인증 상태 배지 + 재인증 UI              │     │
│  └───────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 프로젝트 디렉토리 구조

```
newsletter_system/
├── main.py                    # 엔트리포인트 (CLI: --mode daily|fetch-only|server)
├── launch_webui.py            # Web UI 서버 별도 런처
├── config.yaml                # 운영 설정 (수신자, 폴더 ID, Sheets ID 등)
├── .env                       # API 키 (GNEWS_API_KEY, CLAUDE_API_KEY)
├── requirements.txt           # Python 의존성
├── setup_cron.sh              # 크론 등록 헬퍼 스크립트 (Linux/macOS)
├── run_daily.bat              # Windows 실행 배치 파일
├── task_schedule.xml          # Windows 작업 스케줄러 설정
│
├── src/
│   ├── __init__.py
│   ├── news_service.py       # GNews API 연동 (뉴스 수집)
│   ├── claude_service.py      # Anthropic Claude API 연동 (보고서 생성 + 번역)
│   ├── gmail_service.py       # Gmail API 발송 (OAuth2 + HTML 메일)
│   ├── drive_service.py       # Google Drive API (구글 문서 생성 + 스타일링)
│   ├── notebooklm_service.py  # notebooklm-py 연동 (Playwright 기반 인증, Weekly 원천 자료 저장)
│   ├── db.py                  # Google Sheets 관리 (SheetsDB — 기사 아카이브, 발송 이력)
│   ├── google_auth.py         # Google OAuth2 인증 (토큰 관리, 자동 갱신)
│   ├── prompts.py             # Claude 프롬프트 템플릿 관리
│   ├── email_template.py      # HTML 이메일 템플릿 렌더링
│   └── utils.py               # 유틸리티 (날짜 변환, 마크다운→HTML, retry 데코레이터)
│
├── web_ui/
│   ├── app.py                 # Flask 웹 UI (Daily + Weekly 통합)
│   ├── templates/
│   │   ├── base.html          # 공통 레이아웃 (탭 네비게이션)
│   │   ├── daily.html         # Daily: 키워드 편집 + 미리보기 + 수집 + 생성 + 발행
│   │   └── weekly.html        # Weekly: 기사 선별 + 번역 + 수동 추가 + 생성 + 발행
│   └── static/
│       └── style.css          # 스타일시트
│
├── data/
│   └── newsletters/           # Weekly 마크다운 로컬 백업
│       └── weekly_2026-03-28.md
│
├── credentials/
│   ├── google_credentials.json  # Google OAuth2 클라이언트 시크릿
│   ├── google_token.json        # OAuth2 토큰 (자동 생성)
│   └── storage_state.json       # NotebookLM Playwright 인증 상태
│
├── reference/                     # 기존 Apps Script 코드 (마이그레이션 참조용)
│   ├── Code.gs
│   ├── ClaudeService.gs
│   ├── EmailTemplate.gs
│   ├── GNewsService.gs
│   └── README.md
│
├── tests/                         # 테스트 코드 (pytest)
│
├── logs/
│   ├── spri.log               # 실행 로그
│   └── cron.log               # 스케줄러 실행 로그
│
└── prd/                           # PRD 문서
    ├── SPRi_Newsletter_System_PRD_v1.0.md
    └── SPRi_Newsletter_System_PRD_v1.1.md
```

### 6.3 Google Sheets 스키마

```
시트 1: daily_articles — 수집된 기사
┌─────┬──────────────┬───────┬──────────────┬─────────────┬─────────────┬──────────────┬─────────┐
│ id  │ collected_at │ title │ url (UNIQUE) │ description │ source_name │ published_at │ used_in │
└─────┴──────────────┴───────┴──────────────┴─────────────┴─────────────┴──────────────┴─────────┘

시트 2: manual_articles — 수동 입력 기사
┌─────┬──────────┬───────┬──────────────┬─────────────┬──────────┐
│ id  │ added_at │ title │ url (UNIQUE) │ description │ added_by │
└─────┴──────────┴───────┴──────────────┴─────────────┴──────────┘

시트 3: article_archive — 뉴스레터 인용 아카이브
┌─────┬─────────────────┬──────┬─────────┬───────────────┬─────────────┬─────────────────┐
│ id  │ newsletter_date │ type │ section │ article_title │ article_url │ nlm_notebook_id │
└─────┴─────────────────┴──────┴─────────┴───────────────┴─────────────┴─────────────────┘

시트 4: newsletter_log — 발송 이력
┌─────┬─────────┬──────┬───────────────┬─────────────────┬────────┬───────────────┬──────────────┬──────────────┐
│ id  │ sent_at │ type │ article_count │ recipient_count │ status │ error_message │ drive_doc_id │ nlm_notebook │
└─────┴─────────┴──────┴───────────────┴─────────────────┴────────┴───────────────┴──────────────┴──────────────┘
```

### 6.4 config.yaml 구조

```yaml
# ── 뉴스 수집 ──
gnews:
  queries:
    # 기업/산업
    - "artificial intelligence"
    - "big tech AI"
    - "software industry"
    - "SaaS"
    # 정책/법제
    - "AI regulation"
    - "AI policy"
    # 인력/교육
    - "software developer AI"
    # 기술/연구
    - "AI model"
    # 하드웨어/인프라
    - "AI semiconductor"
    - "AI datacenter"
  lang: "en"
  max_per_query: 25

# ── 뉴스레터 ──
newsletter:
  max_articles: 25
  model: "claude-sonnet-4-20250514"
  max_tokens: 16000

# ── 이메일 수신자 ──
recipients:
  daily:
    - "analyst@spri.kr"
  weekly:
    - "analyst@spri.kr"

# ── Google Sheets (DB) ──
google_sheets:
  spreadsheet_id: "<spreadsheet-id>"

# ── Google Drive ──
drive:
  folder_id: "<folder-id>"

# ── NotebookLM ──
notebooklm:
  notebook_prefix: "SPRi"

# ── 웹 UI ──
web_ui:
  host: "127.0.0.1"
  port: 5000

# ── 로깅 ──
logging:
  level: "INFO"
  file: "logs/spri.log"
```

### 6.5 .env 파일

```
GNEWS_API_KEY=your_gnews_api_key_here
CLAUDE_API_KEY=sk-ant-your_claude_api_key_here
```

---

## 7. CLI 인터페이스

### 7.1 명령어

```bash
# Daily 파이프라인 전체 실행 (스케줄러에 등록할 명령)
python main.py --mode daily

# 웹 UI 서버 시작 (Daily 수동 실행 + Weekly 기사 선별)
python main.py --mode server

# 뉴스 수집만 실행 (테스트용)
python main.py --mode fetch-only

# 웹 UI 별도 런처 (main.py 경유 없이 직접 실행)
python launch_webui.py

# 크론 등록 헬퍼 (Linux/macOS)
bash setup_cron.sh
```

### 7.2 Daily 파이프라인 실행 순서

```
1. config.yaml, .env 로드
2. GNews API 호출 → 기사 수집 (10개 쿼리)
3. 중복 제거 + 25건 제한 → Google Sheets 저장
4. 이전 뉴스레터 요약 조회 (중복 배제용)
5. Claude API 호출 → 뉴스레터 마크다운 생성
6. 마크다운 → HTML 변환
7. Gmail API → Daily 수신자에게 발송
8. Google Drive API → 구글 문서 생성 및 저장 (스타일링 포함)
9. Google Sheets → 발송 이력 기록 + 기사 아카이브
10. 로컬 백업 → data/newsletters/ 에 .md 파일 저장
```

> **참고**: Daily 파이프라인에서는 NotebookLM 저장을 수행하지 않는다 (Weekly만 해당).

### 7.3 스케줄러 등록

**Linux/macOS (crontab)**:
```bash
# setup_cron.sh 내용
#!/bin/bash

# KST 08:00 = UTC 23:00 (전일)
CRON_SCHEDULE="0 23 * * *"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
COMMAND="cd $PROJECT_DIR && $PYTHON_PATH main.py --mode daily >> logs/cron.log 2>&1"

# 기존 크론에 추가
(crontab -l 2>/dev/null; echo "$CRON_SCHEDULE $COMMAND") | crontab -

echo "크론 등록 완료: 매일 KST 08:00 실행"
echo "확인: crontab -l"
```

**Windows 작업 스케줄러**:
```
프로그램: run_daily.bat
시작 위치: C:\Users\...\newsletter_system
트리거: 매일 05:00 KST
설정:
  - 실행 시간 제한: 30분
  - 절전 모드 해제하여 실행: 사용
  - 네트워크 연결 필요: 사용
  - 중복 인스턴스: 무시
  - 실행 수준: 최고 권한
```

`run_daily.bat`:
```batch
@echo off
chcp 65001
cd /d "%~dp0"
python main.py --mode daily >> logs\cron.log 2>&1
```

`task_schedule.xml`: Windows 작업 스케줄러에 직접 임포트 가능한 XML 설정 파일 제공.

---

## 8. 전문가 웹 UI (Daily + Weekly 통합)

### 8.1 구현

Flask로 로컬 웹앱 구현. `http://localhost:5000` 으로 접속.
Daily 탭과 Weekly 탭으로 구분하여 하나의 UI에서 두 가지 뉴스레터를 모두 관리한다.

### 8.2 화면 구성

**[Daily 탭]**

**① 키워드 미리보기 및 편집**
- "키워드 미리보기" 버튼 → config.yaml의 GNews 검색 키워드 표시
- 모달 다이얼로그에서 키워드 추가/삭제/수정 가능 (해당 세션에만 적용)

**② 기사 미리보기 및 수집**
- "기사 미리보기" 버튼 → GNews API 호출 → 수집 결과를 저장 없이 미리 표시
- "뉴스 수집" 버튼 → 미리보기 결과를 재사용하여 Google Sheets에 저장
- 수집된 기사 목록: 제목(링크), 요약, 출처, 발행일
- 오늘 이미 발송된 Daily가 있으면 상단에 "오늘 발송 완료" 배지 표시

**③ Daily 뉴스레터 생성**
- "뉴스레터 생성" 버튼 → Claude API 호출 → 로딩 표시
- 생성된 보고서를 마크다운 에디터에 표시 (전문가 수정 가능)
- SPRi 브랜딩 템플릿으로 HTML 미리보기

**④ 발행**
- "발행" 버튼 → 이메일 발송 + Google Drive 문서 저장을 순차 실행
- 같은 날 이미 발송된 경우 재발송 여부 확인
- 발행 완료 시 상태 표시

**⑤ 초기화**
- "초기화(Reset)" 버튼 → 오늘 수집 기사, 아카이브, 로컬 백업 삭제 (발송 이력은 유지)

**[Weekly 탭]**

**① 기사 선택 화면**
- 한 주간 수집된 Daily 기사를 날짜별로 그룹핑하여 표시
- 각 기사에 체크박스, 제목(링크), 요약, 출처, 발행일 표시
- 상단에 선택 카운터 (`N/25 선택`) 및 전체선택/해제 버튼
- 25건 초과 선택 시 경고

**② 한국어 번역**
- "번역" 버튼 → 선택된 기사의 영문 제목·요약을 Claude API로 한국어 번역
- 전문가의 기사 내용 파악을 돕는 보조 기능

**③ 수동 기사 추가**
- URL 입력 → BeautifulSoup으로 og:title/og:description 자동 추출
- Google Sheets `manual_articles` 시트에 저장
- 수동 기사는 별도 섹션에 그룹핑 표시

**④ 보고서 생성 및 미리보기**
- "주간 보고서 생성" 버튼 → Claude API 호출 → 로딩 표시
- 생성된 보고서를 마크다운 에디터에 표시 (전문가 수정 가능)
- SPRi 브랜딩 템플릿으로 HTML 미리보기

**⑤ 발행**
- "발행" 버튼 → 이메일 발송 + Google Drive 문서 저장 + NotebookLM 소스 저장 + 로컬 백업을 순차 실행
- 발행 완료 시 상태 표시

**⑥ 초기화**
- "초기화(Reset)" 버튼 → 오늘 아카이브, 로컬 백업, NotebookLM 오늘자 소스 삭제 (발송 이력은 유지)

**[공통]**

- **NotebookLM 인증 상태**: 상단에 인증 상태 배지 표시 (유효/만료/미인증)
- **재인증 UI**: "재인증 열기" → Playwright 브라우저 팝업 → Google 로그인 → "재인증 저장"

---

## 9. 인증 및 보안

### 9.1 Google OAuth2

| 항목 | 상세 |
|------|------|
| 자격증명 파일 | `credentials/google_credentials.json` (Google Cloud Console에서 다운로드) |
| 토큰 파일 | `credentials/google_token.json` (최초 인증 시 자동 생성, 이후 자동 갱신) |
| 필요 스코프 | `gmail.send`, `drive.file`, `documents`, `spreadsheets` |
| 인증 흐름 | 최초 실행 시 브라우저 팝업 → 동의 → 토큰 저장 → 이후 자동 갱신 |

### 9.2 notebooklm-py 인증

| 항목 | 상세 |
|------|------|
| 인증 방식 | Playwright 브라우저를 통한 Google 로그인 → 쿠키 저장 |
| 상태 파일 | `credentials/storage_state.json` |
| 갱신 | 쿠키 만료 시 Web UI에서 수동 재인증 필요 |
| Google OAuth2와의 관계 | **별도 인증** — NotebookLM API는 공식 OAuth 스코프를 제공하지 않으므로 Playwright 쿠키 방식을 사용 |

### 9.3 API 키 관리

- GNews API Key, Claude API Key는 `.env` 파일에만 저장
- `.env`는 `.gitignore`에 반드시 포함
- 코드 내에 API 키 하드코딩 금지

---

## 10. 에러 처리

| 상황 | 처리 |
|------|------|
| GNews API 실패 | 재시도 2회 (10초 대기) → 실패 시 에러 로그 기록 |
| Claude API 실패 | 재시도 3회 (30초 대기) → 실패 시 에러 로그 기록 |
| 기사 0건 수집 | "※ 해당 기간 주요 신규 동향 없음" 메시지로 대체 |
| Gmail 발송 실패 | Google Sheets `newsletter_log`에 실패 기록, 에러 로그 |
| Drive 저장 실패 | 에러 로그 기록, 파이프라인은 계속 진행 |
| NotebookLM 저장 실패 | 에러 로그 기록, 파이프라인은 계속 진행 (비핵심 단계) |
| NotebookLM 인증 만료 | Web UI에 만료 배지 표시, 재인증 UI 제공 |
| OAuth 토큰 만료 | 자동 갱신 시도 → 실패 시 재인증 안내 로그 |
| Google Sheets API Rate Limit (429) | 지수 백오프 재시도 |

---

## 11. 로깅

- Python `logging` 모듈 사용
- 로그 파일: `logs/spri.log`
- 로그 레벨: `config.yaml`에서 설정 (기본 `INFO`)
- 모든 파이프라인 단계별 시작/완료/에러 기록
- 스케줄러 실행 시 stdout/stderr → `logs/cron.log`
- Windows 환경 UTF-8 인코딩 대응 (stdout 핸들러)

---

## 12. 의존성 (requirements.txt)

```
# AI
anthropic>=0.40.0

# Google APIs
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0
gspread                          # Google Sheets 연동

# NotebookLM
notebooklm-py>=0.1.0             # https://github.com/teng-lin/notebooklm-py

# 웹 UI
flask>=3.0.0

# 유틸리티
requests>=2.31.0
python-dotenv>=1.0.0
pyyaml>=6.0.0
markdown>=3.5.0
beautifulsoup4>=4.12.0           # URL 메타데이터 추출

# 테스트
pytest>=8.0.0
```

---

## 13. 배포 및 설정 가이드

### 13.1 초기 설정 순서

```
1. 저장소 클론 및 가상환경 생성
   $ git clone <repo-url> && cd newsletter_system
   $ python -m venv venv && source venv/bin/activate  (Windows: venv\Scripts\activate)
   $ pip install -r requirements.txt

2. Google Cloud Console 설정
   - 프로젝트 생성
   - Gmail API, Google Drive API, Google Docs API, Google Sheets API 활성화
   - OAuth2 클라이언트 ID 생성 (데스크톱 앱)
   - credentials/google_credentials.json 다운로드 배치

3. API 키 설정
   - .env 파일에 GNEWS_API_KEY, CLAUDE_API_KEY 입력

4. Google Sheets 설정
   - 새 Google Spreadsheet 생성
   - config.yaml의 google_sheets.spreadsheet_id에 ID 입력
   - 최초 실행 시 시트 탭(daily_articles, manual_articles, article_archive, newsletter_log) 자동 생성

5. config.yaml 수정
   - 수신자 이메일, Drive 폴더 ID, Sheets ID 설정

6. 최초 인증 실행
   $ python main.py --mode fetch-only
   → 브라우저 팝업에서 Google 계정 인증
   → credentials/google_token.json 자동 생성

7. NotebookLM 인증 (선택)
   - Web UI 실행 후 NotebookLM 재인증 UI 사용
   - 또는 Playwright로 storage_state.json 수동 생성

8. 스케줄러 등록 (선택 — PC가 항상 켜져 있는 경우)
   - Linux/macOS: $ bash setup_cron.sh
   - Windows: task_schedule.xml을 작업 스케줄러에 임포트

9. 웹 UI 서버 실행
   $ python main.py --mode server
   → http://localhost:5000 접속하여 Daily/Weekly 모두 관리
```

### 13.2 외부 API 키 발급

| API | 발급 경로 | 비용 |
|-----|-----------|------|
| GNews | https://gnews.io → 회원가입 → API Key | 무료 (100 요청/일) |
| Claude | https://console.anthropic.com → API Keys | 사용량 기반 과금 |
| Google | https://console.cloud.google.com | 무료 (Gmail/Drive/Sheets API 기본 할당량 내) |

### 13.3 notebooklm-py 설정

```
1. pip install notebooklm-py (requirements.txt에 포함)
2. Web UI에서 NotebookLM 재인증 수행
   - "재인증 열기" 클릭 → Playwright 브라우저에서 Google 로그인
   - "재인증 저장" 클릭 → credentials/storage_state.json 생성
3. 쿠키 만료 시 동일 절차로 재인증
4. config.yaml의 notebooklm.notebook_prefix 확인 (기본: "SPRi")
```

---

## 14. 마이그레이션 가이드 (Apps Script → Python)

### 14.1 개요

본 시스템은 기존에 Google Apps Script(JavaScript)로 운영되던 시스템을 로컬 Python으로 마이그레이션한다.
기존 코드는 `reference/` 디렉토리에 보관되며, 구현 시 반드시 참조하여 기존 동작을 보존해야 한다.

### 14.2 파일별 마이그레이션 매핑

| 기존 (.gs) | 신규 (.py) | 마이그레이션 포인트 |
|------------|------------|-------------------|
| `runDailyAutomation.js` | `main.py` | 엔트리포인트, 파이프라인 순서, **HTML 템플릿 구조·인라인 CSS 그대로 보존** |
| `config.js` | `src/claude_service.py` | 모델명 보존 |
| `api_key.js` | `.env` | api_key 제공 |
| (GmailApp 내장) | `src/gmail_service.py` | Apps Script `GmailApp.sendEmail()` → Gmail API + OAuth2 |
| (DriveApp 내장) | `src/drive_service.py` | Apps Script `DocumentApp` → Google Drive/Docs API |
| (SpreadsheetApp 내장) | `src/db.py` | Apps Script `SpreadsheetApp` → gspread (Google Sheets 구조 유사하게 유지) |
| (없음, 신규) | `src/notebooklm_service.py` | 신규 추가 — notebooklm-py 연동 (Playwright 인증) |
| (없음, 신규) | `src/google_auth.py` | 신규 추가 — OAuth2 토큰 관리 |
| (없음, 신규) | `web_ui/app.py` | 신규 추가 — Daily+Weekly 통합 웹 UI |

### 14.3 반드시 보존해야 할 요소

1. **Claude 프롬프트 전문**: `reference/` 내 프롬프트 텍스트를 `src/prompts.py`에 그대로 옮길 것. 변수 치환 방식만 JavaScript 템플릿 리터럴(`${var}`)에서 Python f-string 또는 `.format()`으로 변환.
2. **HTML 이메일 템플릿**: 인라인 CSS, 색상값(`#1a2a3a`, `#2d5a8e`), 레이아웃 구조를 그대로 유지할 것. 이메일 클라이언트 호환성이 검증된 상태이므로 구조 변경 금지.
3. **Claude API 호출 파라미터**: 모델명, `max_tokens`, `anthropic-version` 헤더 등을 기존 코드와 동일하게 설정할 것.
4. **GNews 후처리 로직**: 중복 제거, 정렬, 25건 제한 등의 로직을 보존할 것.
5. **마크다운 → HTML 변환 규칙**: `## → <h2>`, `** → <strong>`, `* [title](url) → 📎 <a>` 변환 패턴을 그대로 보존할 것.

---

## 15. 향후 확장 고려사항

- **뉴스 소스 추가**: GNews 외 추가 뉴스 API 연동
- **NotebookLM 분석 활용**: 저장된 소스 기반으로 NotebookLM의 AI 요약·Q&A 기능 활용
- **관심 뉴스 피드백 루프**: 수신자 피드백을 뉴스수집 개선에 반영
- **Docker 컨테이너화**: 환경 일관성을 위한 Docker 이미지 제공
- **Telegram 알림**: 뉴스레터 발송 완료 시 Telegram 메신저 알림

---

## 부록 A. GNews API 호출 사양

```
GET https://gnews.io/api/v4/search
  ?q={keyword}
  &lang=en
  &from={ISO8601_24h_ago}
  &max=25
  &apikey={GNEWS_API_KEY}

Response (주요 필드):
{
  "articles": [
    {
      "title": "기사 제목",
      "description": "기사 요약",
      "url": "기사 permalink",
      "publishedAt": "2026-03-29T01:00:00Z",
      "source": { "name": "출처명", "url": "출처 URL" }
    }
  ]
}
```

## 부록 B. Claude API 호출 사양

```
POST https://api.anthropic.com/v1/messages
Headers:
  Content-Type: application/json
  x-api-key: {CLAUDE_API_KEY}
  anthropic-version: 2023-06-01

Body:
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 16000,
  "messages": [
    { "role": "user", "content": "{프롬프트 본문}" }
  ]
}

Response:
{
  "content": [
    { "type": "text", "text": "생성된 보고서 본문" }
  ]
}
```

## 부록 C. notebooklm-py API 참조

```
Repository: https://github.com/teng-lin/notebooklm-py

인증 방식:
- Playwright 브라우저 자동화를 통한 Google 쿠키 인증
- storage_state.json 파일로 세션 상태 저장/복원

주요 메서드 (라이브러리 문서 참조):
- NotebookLMClient(storage_state)   # 인증된 클라이언트 생성
- .list_notebooks()                 # 노트북 목록 조회
- .create_notebook(title)           # 새 노트북 생성
- .add_source(notebook_id, ...)     # 소스 추가 (URL, 텍스트 등)
- .get_notebook(notebook_id)        # 노트북 상세 조회

적용 범위: Weekly 발행 시에만 사용 (Daily에서는 미사용)

※ 정확한 메서드 시그니처는 라이브러리 최신 문서를 참조할 것.
  실제 구현 시 라이브러리 소스코드(GitHub)를 확인하여 호환성 검증 필요.
```
