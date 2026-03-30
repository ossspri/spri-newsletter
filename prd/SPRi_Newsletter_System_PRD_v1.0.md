# SPRi 뉴스레터 자동화 시스템 PRD

> **Product Requirements Document**
> 문서 버전: 1.0 | 작성일: 2026-03-29 | 상태: Draft

---

## 1. 개요

### 1.1 프로덕트 요약

소프트웨어정책연구소(SPRi)의 글로벌 SW 산업 동향 뉴스레터를 자동으로 수집·생성·배포하는 **로컬 실행 시스템**.
Daily와 Weekly 두 가지 주기로 운영하며, 로컬 머신에서 Python으로 동작한다.
Daily는 OS 크론 자동 실행과 전문가 수동 실행을 모두 지원하고, Weekly는 전문가가 UI에서 기사를 선별하여 생성한다.
원천 자료는 notebooklm-py를 통해 Google NotebookLM에 저장하고, 보고서는 Google Drive에 구글 문서로 저장한다.

### 1.2 배경 및 목적

- SPRi 산업분석팀이 수작업으로 수행하던 뉴스 큐레이션·보고서 작성·배포 업무를 자동화
- 매일 일관된 품질의 산업 동향 브리핑을 정시 발송하되, PC가 꺼져 있을 때는 전문가가 수동으로도 실행 가능
- 전문가는 주간 보고서의 기사 선별과 최종 검토에만 집중
- NotebookLM을 기사 아카이브 및 분석 허브로 활용

### 1.3 기술 스택

| 항목 | 선택 | 근거 |
|------|------|------|
| 런타임 | Python 3.11+ (로컬) | 로컬 실행, 풍부한 라이브러리 생태계 |
| 스케줄러 | OS 네이티브 크론 (macOS/Linux: `crontab`, Windows: 작업 스케줄러) | 외부 서비스 의존 없이 정시 자동 실행 |
| 뉴스 수집 | GNews API (gnews.io) | REST API, 시간 필터링 지원, 무료 티어 제공 |
| AI 생성 | Anthropic Claude API (`claude-sonnet-4-20250514`) | 한국어 고품질 보고서 생성, 프롬프트 제어 용이 |
| 이메일 발송 | Gmail API (google-api-python-client) | OAuth2 인증, HTML 메일 지원 |
| 보고서 저장 | Google Drive API (google-api-python-client) | 구글 문서 자동 생성 |
| 원천 자료 저장 | notebooklm-py (https://github.com/teng-lin/notebooklm-py) | NotebookLM에 기사 URL 건별 저장, 주간 노트북 관리 |
| 로컬 데이터 | SQLite | 기사 아카이브, 발송 이력, 설정값 로컬 관리 |
| Weekly UI | 로컬 웹 UI (Flask 또는 Streamlit) | 전문가가 브라우저에서 Daily 수동 실행 및 Weekly 기사 선별·발송 지시 |
| 설정 관리 | `.env` 파일 + `config.yaml` | API 키는 환경변수, 운영 설정은 YAML |

---

## 2. 사용자 및 역할

| 역할 | 설명 | 주요 행동 |
|------|------|-----------|
| 시스템 (자동) | OS 크론으로 Daily 파이프라인 실행 | 뉴스 수집 → 보고서 생성 → 이메일 발송 → Drive/NotebookLM 저장 |
| 전문가 (수동) | SPRi 산업분석 담당자 | Daily 수동 실행 (크론 미작동 시), Weekly 기사 선별, 보고서 검토/수정, 발송 지시 |
| 수신자 | 뉴스레터 구독자 | 이메일 수신 (Daily/Weekly 그룹 분리) |

---

## 3. 기능 요구사항

### 3.1 뉴스 기사 수집

#### 3.1.1 자동 수집 (Daily)

- **API**: GNews API (`https://gnews.io/api/v4/search`)
- **검색 키워드** (6개 쿼리를 순차 호출):
  1. `software`
  2. `SaaS`
  3. `AI regulation`
  4. `AI policy`
  5. `big tech AI`
  6. `AI semiconductor GPU`
  7. `software developer`
  8. `AI research breakthrough`
- **필터 조건**:
  - `from`: 현재 시각 기준 24시간 이전 (ISO 8601)
  - `lang`: `en`
  - `max`: 쿼리당 50건
- **후처리**:
  - URL 기준 중복 제거
  - 발행일 기준 최신순 정렬
  - 최대 25건으로 제한
- **저장**: 수집 결과를 로컬 SQLite `daily_articles` 테이블에 기록

#### 3.1.2 수동 수집 (Weekly 보완용)

- 전문가가 Weekly UI에서 기사 URL을 직접 입력
- 시스템이 URL에서 제목·요약을 자동 추출하여 SQLite에 저장

### 3.2 뉴스레터 생성

#### 3.2.1 Daily 뉴스레터

- **트리거 (이중 방식)**:
  - **자동**: OS 크론 (`crontab -e` 또는 Windows 작업 스케줄러) — PC가 켜져 있을 때 정시 실행
  - **수동**: 전문가가 로컬 웹 UI에서 "Daily 뉴스레터 생성" 버튼 클릭 — PC가 꺼져 있었거나 크론이 실패했을 때 수시 실행
- **실행 명령 (자동)**: `python main.py --mode daily`
- **중복 방지**: 같은 날 이미 Daily가 발송된 경우, 수동 실행 시 "오늘 이미 발송됨" 경고를 표시하고 전문가가 재발송 여부를 선택
- **입력**: 자동 수집된 기사 목록 (최대 25건)
- **처리**: Claude API 호출하여 SPRi 양식 보고서 생성
- **출력**: 마크다운 형식의 뉴스레터 본문

#### 3.2.2 Weekly 보고서

- **트리거**: 전문가가 로컬 웹 UI에서 "생성" 버튼 클릭
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
| 출처 형식 | `* [기사 제목](기사 직접 URL)` — permalink만 사용 |
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

---

## 4. 산출물 저장

### 4.1 보고서 저장 (Google Drive)

| 항목 | 상세 |
|------|------|
| 형식 | 구글 문서 (Google Docs) |
| 위치 | Google Drive 내 지정 폴더 (`config.yaml`의 `drive_folder_id`) |
| 명명 규칙 | `SPRi_일간브리핑_YYYY-MM-DD` / `SPRi_주간동향_YYYY-MM-DD` |
| 구현 | Google Drive API (`googleapiclient`) 로 구글 문서 생성 후 폴더 이동 |

### 4.2 원천 자료 저장 (NotebookLM)

| 항목 | 상세 |
|------|------|
| 라이브러리 | `notebooklm-py` (https://github.com/teng-lin/notebooklm-py) |
| 저장 단위 | 뉴스레터에 인용된 기사의 URL 건별 |
| 노트북 구조 | 주 단위로 노트북 생성 (예: `SPRi_2026_W14`) |
| 저장 흐름 | 뉴스레터 생성 완료 → 인용된 기사 URL을 해당 주간 노트북에 소스로 추가 |

#### 4.2.1 NotebookLM 연동 상세

```python
# notebooklm-py 사용 흐름 (의사코드)

# 1. 인증: Google OAuth2 자격증명 재사용
from notebooklm import NotebookLM
nlm = NotebookLM(credentials=google_credentials)

# 2. 주간 노트북 확인 또는 생성
week_label = "SPRi_2026_0330"  # 해당 주의 월요일 날짜
notebook = nlm.get_or_create_notebook(title=week_label)

# 3. 기사 URL을 소스로 추가 (건별)
for article in newsletter_articles:
    notebook.add_source(
        source_type="url",
        url=article["url"],
        title=article["title"]
    )

# 4. (선택) 생성된 뉴스레터 본문도 텍스트 소스로 추가
notebook.add_source(
    source_type="text",
    text=newsletter_markdown,
    title=f"Daily_브리핑_{date_str}"
)
```

#### 4.2.2 NotebookLM 노트북 명명 규칙

| 주기 | 노트북 제목 형식 | 예시 |
|------|----------------|------|
| 주간 | `SPRi_{연도}_{해당 주의 월요일 날짜}` | `SPRi_2026_0330` |

하나의 주간 노트북에 해당 주의 모든 Daily 기사 URL과 뉴스레터 본문이 누적 저장된다.

### 4.3 로컬 아카이브 (SQLite)

원천 자료의 주 저장소는 NotebookLM이지만, 로컬 SQLite에도 메타데이터를 보관하여 중복 검사 및 Weekly 기사 선별 UI에 활용한다.

---

## 5. 이메일 배포

### 5.1 발송 방식

| 구분 | Daily | Weekly |
|------|-------|--------|
| 트리거 | OS 크론 자동 실행 **또는** 전문가가 웹 UI에서 수동 실행 | 전문가가 로컬 웹 UI에서 "발송" 클릭 |
| 수신자 | `config.yaml`의 `recipients_daily` | `config.yaml`의 `recipients_weekly` |
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
└── 푸터 (회색 배경, 11px, 중앙 정렬)
    └── "SPRi 소프트웨어정책연구소 | 본 뉴스레터는 AI 기반으로 자동 생성되었습니다"
```

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
│  │ OS 크론   │───▶│ main.py       │───▶│ GNews API    │             │
│  │ (crontab) │    │ --mode daily  │    │ 뉴스 수집     │             │
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
│  │ Gmail   │ │ Google  │ │ Notebook  │ │ SQLite       │           │
│  │ API     │ │ Drive   │ │ LM        │ │ (로컬 DB)    │           │
│  │ 발송    │ │ API     │ │ (nlm-py)  │ │ 아카이브     │           │
│  │         │ │ 문서저장 │ │ URL저장   │ │ + 이력관리   │           │
│  └─────────┘ └─────────┘ └───────────┘ └──────────────┘           │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │       로컬 웹 UI (Flask/Streamlit) — Daily + Weekly 통합    │     │
│  │  http://localhost:5000                                     │     │
│  │                                                            │     │
│  │  [Daily 탭]                        [Weekly 탭]             │     │
│  │  • "뉴스 수집" 버튼               • 주간 기사 목록 (체크박스) │     │
│  │  • "Daily 뉴스레터 생성" 버튼     • "주간 보고서 생성" 버튼   │     │
│  │  • 미리보기 → "발송" 버튼         • 미리보기 → "발송" 버튼   │     │
│  │  • 오늘 발송 이력 표시             • 수동 기사 추가           │     │
│  └───────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
```

### 6.2 프로젝트 디렉토리 구조

```
spri-newsletter/
├── main.py                    # 엔트리포인트 (CLI: --mode daily|server)
├── config.yaml                # 운영 설정 (수신자, 폴더 ID, 스케줄 등)
├── .env                       # API 키 (GNEWS_API_KEY, CLAUDE_API_KEY)
├── requirements.txt           # Python 의존성
├── setup_cron.sh              # 크론 등록 헬퍼 스크립트
│
├── src/
│   ├── __init__.py
│   ├── news_service.py       # GNews API 연동 (뉴스 수집)
│   ├── claude_service.py      # Anthropic Claude API 연동 (보고서 생성)
│   ├── gmail_service.py       # Gmail API 발송 (OAuth2 + HTML 메일)
│   ├── drive_service.py       # Google Drive API (구글 문서 생성)
│   ├── notebooklm_service.py  # notebooklm-py 연동 (원천 자료 저장)
│   ├── db.py                  # SQLite 관리 (기사 아카이브, 발송 이력)
│   ├── prompts.py             # Claude 프롬프트 템플릿 관리
│   ├── email_template.py      # HTML 이메일 템플릿 렌더링
│   └── utils.py               # 유틸리티 (날짜 변환, 마크다운→HTML 등)
│
├── web_ui/
│   ├── app.py                 # Flask/Streamlit 웹 UI (Daily + Weekly 통합)
│   ├── templates/
│   │   ├── base.html          # 공통 레이아웃 (탭 네비게이션)
│   │   ├── daily.html         # Daily 뉴스 수집 + 생성 + 발송
│   │   └── weekly.html        # Weekly 기사 선별 + 생성 + 발송
│   └── static/
│       └── style.css
│
├── data/
│   ├── spri_newsletter.db     # SQLite 데이터베이스
│   └── newsletters/           # 생성된 뉴스레터 마크다운 로컬 백업
│       ├── daily_2026-03-29.md
│       └── weekly_2026-03-28.md
│
├── credentials/
│   ├── google_credentials.json  # Google OAuth2 클라이언트 시크릿
│   └── google_token.json        # OAuth2 토큰 (자동 생성)
│
├── reference/                     # ★ 기존 Apps Script 코드 (마이그레이션 참조용)
│   ├── Code.gs                    #   메인 로직 (엔트리포인트)
│   ├── ClaudeService.gs           #   Claude API 호출 + 프롬프트
│   ├── EmailTemplate.gs           #   HTML 이메일 템플릿
│   ├── GNewsService.gs            #   GNews API 연동
│   └── README.md                  #   기존 코드 구조 설명
│
└── logs/
    └── spri.log               # 실행 로그
```

> **`reference/` 디렉토리 안내**
> 이 디렉토리에는 Google Apps Script(JavaScript)로 이미 동작하던 기존 시스템의 소스 코드가 들어있다.
> Python 마이그레이션 시 다음 요소를 반드시 참조하여 기존 동작을 보존할 것:
> - **HTML 이메일 템플릿**: 헤더/본문/푸터 구조, 인라인 CSS, SPRi 브랜딩 색상
> - **Claude 모델 및 API 키 설정**: 모델명, 파라미터, 헤더 구성
> - **마크다운 → HTML 변환 규칙**: 허용된 마크다운 문법과 변환 로직
>
> 기존 .gs 파일은 실행 대상이 아니며, 오직 참조용이다. `reference/` 내 코드는 빌드·배포에 포함하지 않는다.

### 6.3 SQLite 스키마

```sql
-- 수집된 기사
CREATE TABLE daily_articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at  TEXT NOT NULL,          -- 수집 일시 (ISO 8601)
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,   -- 중복 방지
    description   TEXT,
    source_name   TEXT,
    published_at  TEXT NOT NULL,          -- 기사 발행일
    used_in       TEXT DEFAULT NULL       -- 사용된 뉴스레터 유형 (daily/weekly/null)
);

-- 수동 입력 기사
CREATE TABLE manual_articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    added_at      TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    description   TEXT,
    added_by      TEXT DEFAULT 'expert'
);

-- 뉴스레터 인용 아카이브
CREATE TABLE article_archive (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    newsletter_date TEXT NOT NULL,
    newsletter_type TEXT NOT NULL,        -- 'daily' | 'weekly'
    section         TEXT,                 -- 섹션명
    article_title   TEXT NOT NULL,
    article_url     TEXT NOT NULL,
    nlm_notebook_id TEXT                  -- NotebookLM 노트북 식별자
);

-- 발송 이력
CREATE TABLE newsletter_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at         TEXT NOT NULL,
    type            TEXT NOT NULL,        -- 'daily' | 'weekly'
    article_count   INTEGER,
    recipient_count INTEGER,
    status          TEXT NOT NULL,        -- 'success' | 'failed'
    error_message   TEXT DEFAULT NULL,
    drive_doc_id    TEXT DEFAULT NULL,    -- 저장된 구글 문서 ID
    nlm_notebook    TEXT DEFAULT NULL     -- 저장된 NotebookLM 노트북명
);
```

### 6.4 config.yaml 구조

```yaml
# ── 뉴스 수집 ──
gnews:
  queries:
    - "software industry AI"
    - "AI regulation policy"
    - "big tech AI strategy"
    - "AI semiconductor GPU"
    - "software developer AI"
    - "AI research breakthrough"
  lang: "en"
  max_per_query: 50

# ── 뉴스레터 ──
newsletter:
  max_articles: 25
  model: "claude-sonnet-4-20250514"
  max_tokens: 4096

# ── 이메일 수신자 ──
recipients:
  daily:
    - "analyst1@spri.kr"
    - "analyst2@spri.kr"
  weekly:
    - "director@spri.kr"
    - "team-lead@spri.kr"

# ── Google Drive ──
drive:
  folder_id: "1aBcDeFgHiJkLmNoPqRsT"  # 보고서 저장 폴더 ID

# ── NotebookLM ──
notebooklm:
  notebook_prefix: "SPRi"               # 노트북 제목 접두사
  # 노트북명 형식: {prefix}_{연도}_W{ISO주차}

# ── 스케줄 ──
schedule:
  daily_time: "06:00"                    # KST 기준 Daily 발송 시각

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
# Daily 파이프라인 전체 실행 (크론에 등록할 명령)
python main.py --mode daily

# 웹 UI 서버 시작 (Daily 수동 실행 + Weekly 기사 선별)
python main.py --mode server

# 뉴스 수집만 실행 (테스트용)
python main.py --mode fetch-only

# 크론 등록 헬퍼
bash setup_cron.sh
```

> **참고**: `--mode daily`는 크론이 호출하는 헤드리스 모드이고, `--mode server`는 전문가가 웹 브라우저로 접속하여 Daily/Weekly를 모두 조작할 수 있는 UI 모드이다.

### 7.2 Daily 파이프라인 실행 순서

```
1. config.yaml, .env 로드
2. GNews API 호출 → 기사 수집 (6개 쿼리)
3. 중복 제거 + 25건 제한 → SQLite 저장
4. 이전 뉴스레터 요약 조회 (중복 배제용)
5. Claude API 호출 → 뉴스레터 마크다운 생성
6. 마크다운 → HTML 변환
7. Gmail API → Daily 수신자에게 발송
8. Google Drive API → 구글 문서 생성 및 저장
9. notebooklm-py → 해당 주간 노트북에 기사 URL 저장
10. SQLite → 발송 이력 기록
11. 로컬 백업 → data/newsletters/ 에 .md 파일 저장
```

### 7.3 크론 등록 예시

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
프로그램: python
인수: main.py --mode daily
시작 위치: C:\path\to\spri-newsletter
트리거: 매일 08:00
```

---

## 8. 전문가 웹 UI (Daily + Weekly 통합)

### 8.1 구현

Flask 또는 Streamlit으로 로컬 웹앱 구현. `http://localhost:5000` 으로 접속.
Daily 탭과 Weekly 탭으로 구분하여 하나의 UI에서 두 가지 뉴스레터를 모두 관리한다.

### 8.2 화면 구성

**[Daily 탭]**

**① 뉴스 수집**
- "뉴스 수집 (24h)" 버튼 → GNews API 호출 → 수집 결과 표시
- 수집된 기사 목록: 제목(링크), 요약, 출처, 발행일
- 오늘 이미 발송된 Daily가 있으면 상단에 "오늘 발송 완료" 배지 표시

**② Daily 뉴스레터 생성**
- "Daily 뉴스레터 생성" 버튼 → Claude API 호출 → 로딩 표시
- 생성된 보고서를 SPRi 브랜딩 템플릿으로 미리보기
- 전문가가 내용 직접 수정 가능 (텍스트 에디터)

**③ 발송 및 저장**
- "이메일 발송" 버튼 → Daily 수신자에게 발송
- 같은 날 이미 발송된 경우 "오늘 이미 발송됨. 재발송하시겠습니까?" 확인 대화상자 표시
- "Drive 저장" 버튼 → 지정 폴더에 구글 문서로 저장
- 발송/저장 완료 시 상태 표시

**[Weekly 탭]**

**① 기사 선택 화면**
- 한 주간 수집된 Daily 기사를 날짜별로 그룹핑하여 표시
- 각 기사에 체크박스, 제목(링크), 요약, 출처, 발행일 표시
- 상단에 선택 카운터 (`N/25 선택`) 및 전체선택/해제 버튼
- 25건 초과 선택 시 경고
- 수동 기사 추가 입력 필드 (URL 입력 → 자동 메타 추출)

**② 보고서 생성 및 미리보기**
- "주간 보고서 생성" 버튼 → Claude API 호출 → 로딩 표시
- 생성된 보고서를 SPRi 브랜딩 템플릿으로 미리보기
- 전문가가 내용 직접 수정 가능 (텍스트 에디터)

**③ 발송 및 저장**
- "이메일 발송" 버튼 → Weekly 수신자에게 발송
- "Drive 저장" 버튼 → 지정 폴더에 구글 문서로 저장
- 발송/저장 완료 시 상태 표시

---

## 9. 인증 및 보안

### 9.1 Google OAuth2

| 항목 | 상세 |
|------|------|
| 자격증명 파일 | `credentials/google_credentials.json` (Google Cloud Console에서 다운로드) |
| 토큰 파일 | `credentials/google_token.json` (최초 인증 시 자동 생성, 이후 자동 갱신) |
| 필요 스코프 | `gmail.send`, `drive.file`, `documents` |
| 인증 흐름 | 최초 실행 시 브라우저 팝업 → 동의 → 토큰 저장 → 이후 자동 갱신 |

### 9.2 notebooklm-py 인증

- Google OAuth2 자격증명을 공유 사용 (별도 인증 불필요)
- `notebooklm-py`가 내부적으로 Google 인증 세션 재사용

### 9.3 API 키 관리

- GNews API Key, Claude API Key는 `.env` 파일에만 저장
- `.env`는 `.gitignore`에 반드시 포함
- 코드 내에 API 키 하드코딩 금지

---

## 10. 에러 처리

| 상황 | 처리 |
|------|------|
| GNews API 실패 | 재시도 2회 (10초 대기) → 실패 시 관리자에게 에러 알림 이메일 |
| Claude API 실패 | 재시도 3회 (30초 대기) → 실패 시 수집된 기사 목록만 이메일로 발송 |
| 기사 0건 수집 | "※ 해당 기간 주요 신규 동향 없음" 메시지로 대체하여 이메일 발송 |
| Gmail 발송 실패 | SQLite `newsletter_log`에 실패 기록, 관리자에게 별도 에러 알림 |
| Drive 저장 실패 | 로컬 마크다운 백업은 유지, 에러 로그 기록 |
| NotebookLM 저장 실패 | 에러 로그 기록, 파이프라인은 계속 진행 (비핵심 단계) |
| OAuth 토큰 만료 | 자동 갱신 시도 → 실패 시 재인증 안내 로그 |

---

## 11. 로깅

- Python `logging` 모듈 사용
- 로그 파일: `logs/spri.log` (일별 로테이션)
- 로그 레벨: `config.yaml`에서 설정 (기본 `INFO`)
- 모든 파이프라인 단계별 시작/완료/에러 기록
- 크론 실행 시 stdout/stderr → `logs/cron.log`

---

## 12. 의존성 (requirements.txt)

```
# AI
anthropic>=0.40.0

# Google APIs
google-api-python-client>=2.100.0
google-auth-httplib2>=0.2.0
google-auth-oauthlib>=1.2.0

# NotebookLM
notebooklm-py>=0.1.0    # https://github.com/teng-lin/notebooklm-py

# 웹 UI (Daily + Weekly 통합)
flask>=3.0.0
# 또는 streamlit>=1.30.0

# 유틸리티
requests>=2.31.0
python-dotenv>=1.0.0
pyyaml>=6.0.0
markdown>=3.5.0

# (선택) URL 메타 추출
beautifulsoup4>=4.12.0
```

---

## 13. 배포 및 설정 가이드

### 13.1 초기 설정 순서

```
1. 저장소 클론 및 가상환경 생성
   $ git clone <repo-url> && cd spri-newsletter
   $ python -m venv venv && source venv/bin/activate
   $ pip install -r requirements.txt

2. 기존 Apps Script 코드 배치
   - reference/ 디렉토리에 기존 .gs 파일 복사
   - 마이그레이션 참조용이며, 실행 대상 아님

3. Google Cloud Console 설정
   - 프로젝트 생성
   - Gmail API, Google Drive API, Google Docs API 활성화
   - OAuth2 클라이언트 ID 생성 (데스크톱 앱)
   - credentials/google_credentials.json 다운로드 배치

4. API 키 설정
   - .env 파일에 GNEWS_API_KEY, CLAUDE_API_KEY 입력

5. config.yaml 수정
   - 수신자 이메일, Drive 폴더 ID, 스케줄 시간 설정

6. 최초 인증 실행
   $ python main.py --mode fetch-only
   → 브라우저 팝업에서 Google 계정 인증
   → credentials/google_token.json 자동 생성

7. 크론 등록 (선택 — PC가 항상 켜져 있는 경우)
   $ bash setup_cron.sh

8. 웹 UI 서버 실행
   $ python main.py --mode server
   → http://localhost:5000 접속하여 Daily/Weekly 모두 관리
```

### 13.2 외부 API 키 발급

| API | 발급 경로 | 비용 |
|-----|-----------|------|
| GNews | https://gnews.io → 회원가입 → API Key | 무료 (100 요청/일) |
| Claude | https://console.anthropic.com → API Keys | 사용량 기반 과금 |
| Google | https://console.cloud.google.com | 무료 (Gmail/Drive API 기본 할당량 내) |

### 13.3 notebooklm-py 설정

```
1. pip install notebooklm-py
2. Google OAuth2 자격증명 공유 (credentials/ 디렉토리)
3. 최초 실행 시 NotebookLM 접근 권한 동의
4. config.yaml의 notebooklm.notebook_prefix 확인
```

---

## 14. 마이그레이션 가이드 (Apps Script → Python)

### 14.1 개요

본 시스템은 기존에 Google Apps Script(JavaScript)로 운영되던 시스템을 로컬 Python으로 마이그레이션한다.
기존 코드는 `reference/` 디렉토리에 보관되며, 구현 시 반드시 참조하여 기존 동작을 보존해야 한다.

### 14.2 파일별 마이그레이션 매핑

| 기존 (.gs) | 신규 (.py) | 마이그레이션 포인트 |
|------------|------------|-------------------|
| `runDailyAutomation.js` | `main.py` | 엔트리포인트, 파이프라인 순서, **HTML 템플릿 구조·인라인 CSS 그대로 보존**  |
| `config.js` | `src/claude_service.py` | 모델명 보존 |
| `api_key.js` | `.env` | api_key 제공 |
| (GmailApp 내장) | `src/gmail_service.py` | Apps Script `GmailApp.sendEmail()` → Gmail API + OAuth2 |
| (DriveApp 내장) | `src/drive_service.py` | Apps Script `DocumentApp` → Google Drive/Docs API |
| (없음, 신규) | `src/notebooklm_service.py` | 신규 추가 — notebooklm-py 연동 |
| (없음, 신규) | `web_ui/app.py` | 신규 추가 — Daily+Weekly 통합 웹 UI |

### 14.3 반드시 보존해야 할 요소

1. **Claude 프롬프트 전문**: `reference/` 내 프롬프트 텍스트를 `src/prompts.py`에 그대로 옮길 것. 변수 치환 방식만 JavaScript 템플릿 리터럴(`${var}`)에서 Python f-string 또는 `.format()`으로 변환.
2. **HTML 이메일 템플릿**: 인라인 CSS, 색상값(`#1a2a3a`, `#2d5a8e`), 레이아웃 구조를 그대로 유지할 것. 이메일 클라이언트 호환성이 검증된 상태이므로 구조 변경 금지.
3. **Claude API 호출 파라미터**: 모델명, `max_tokens`, `anthropic-version` 헤더 등을 기존 코드와 동일하게 설정할 것.
4. **GNews 후처리 로직**: 중복 제거, 정렬, 25건 제한 등의 로직을 보존할 것.
5. **마크다운 → HTML 변환 규칙**: `## → <h2>`, `** → <strong>`, `* [title](url) → 📎 <a>` 변환 패턴을 그대로 보존할 것.

### 14.4 Claude Code 작업 지시 예시

```
이 프로젝트의 PRD.md를 먼저 읽어주세요.
그 다음 reference/ 디렉토리의 기존 Apps Script(.gs) 파일들을 분석하고,
PRD의 기능 요구사항에 따라 Python으로 마이그레이션해주세요.

주의사항:
- reference/ 내 Claude 프롬프트 원문과 HTML 이메일 템플릿은 그대로 보존
- Apps Script 전용 API(GmailApp, DriveApp 등)는 Google Python Client로 교체
- Google Sheets 대신 SQLite 사용
- notebooklm-py 연동은 신규 구현
- web_ui/는 Flask로 신규 구현 (Daily+Weekly 통합)
```

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
  &max=10
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
  "max_tokens": 4096,
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

주요 메서드 (라이브러리 문서 참조):
- NotebookLM(credentials)         # 인증된 클라이언트 생성
- .list_notebooks()               # 노트북 목록 조회
- .create_notebook(title)         # 새 노트북 생성
- .add_source(notebook_id, ...)   # 소스 추가 (URL, 텍스트 등)
- .get_notebook(notebook_id)      # 노트북 상세 조회

※ 정확한 메서드 시그니처는 라이브러리 최신 문서를 참조할 것.
  실제 구현 시 라이브러리 소스코드(GitHub)를 확인하여 호환성 검증 필요.
```
