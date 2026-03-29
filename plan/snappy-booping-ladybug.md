# SPRi 뉴스레터 시스템 — Claude Skill/도구 활용 분석

## Context
SPRi 뉴스레터 자동화 시스템 PRD(v1.0)의 요구사항을 검토하고, Claude Code에서 제공하는 Skill 및 MCP 도구 중 개발·운영에 활용할 수 있는 것들을 조사한다.

---

## 1. 직접 활용 가능한 Skill/도구

### 1-1. `claude-api` Skill — **핵심 활용**
- **관련 요구사항**: PRD 3.2 (뉴스레터 생성), 부록 B (Claude API 호출 사양)
- **활용 방법**: `src/claude_service.py` 구현 시 이 스킬을 호출하면 Anthropic SDK 사용 패턴, 모델 호출, 에러 처리 등의 best practice 코드를 빠르게 생성할 수 있음
- **구체적 도움**:
  - `anthropic` Python SDK를 사용한 Messages API 호출 코드 작성
  - PRD에 명시된 `claude-sonnet-4-20250514` 모델, `max_tokens: 4096` 파라미터 설정
  - 재시도 로직 (PRD 10절: 3회 재시도, 30초 대기)

### 1-2. `schedule` Skill — **운영 자동화**
- **관련 요구사항**: PRD 3.2.1 (Daily 뉴스레터 크론 자동 실행), 7.3 (크론 등록)
- **활용 방법**: OS 크론 대신 또는 보완으로 Claude Code의 원격 스케줄 에이전트를 설정하여 Daily 파이프라인을 정시 실행할 수 있음
- **주의사항**: PRD는 로컬 Python 실행을 전제하므로, 원격 트리거가 로컬 스크립트를 실행하는 방식의 연동이 필요. OS 크론의 완전한 대체보다는 **보조 수단** 또는 **모니터링 용도**로 적합

### 1-3. `simplify` Skill — **코드 품질**
- **관련 요구사항**: 전체 구현 후 코드 리뷰
- **활용 방법**: 각 모듈(`news_service.py`, `claude_service.py` 등) 구현 후 이 스킬로 코드 품질, 중복, 효율성을 점검

### 1-4. Gmail MCP 도구 — **테스트/프로토타이핑**
- **관련 요구사항**: PRD 5절 (이메일 배포)
- **사용 가능 도구**:
  - `gmail_create_draft` — 뉴스레터 초안 작성 테스트
  - `gmail_search_messages` — 기존 발송 이력 확인
  - `gmail_read_message` — 수신된 뉴스레터 내용 검증
  - `gmail_get_profile` — OAuth 연결 상태 확인
  - `gmail_list_labels` — 뉴스레터 관련 라벨 구성 확인
- **활용 방법**: `src/gmail_service.py` 개발 전에 MCP 도구로 Gmail API 동작을 빠르게 프로토타이핑하고, 실제 메일 발송 테스트를 수행할 수 있음

### 1-5. `loop` Skill — **개발 중 모니터링**
- **관련 요구사항**: PRD 10절 (에러 처리), 11절 (로깅)
- **활용 방법**: 개발/테스트 중 주기적으로 로그 파일이나 파이프라인 상태를 모니터링하는 데 활용 가능

---

## 2. 간접 활용 가능한 도구

### 2-1. Notion MCP 도구 — **프로젝트 관리 보조**
- PRD의 핵심 기능과 직접 관련은 없음 (PRD는 NotebookLM 사용)
- 그러나 프로젝트 진행 상황 추적, 마이그레이션 체크리스트, 이슈 관리 등을 Notion으로 할 경우 활용 가능
- `notion-create-pages`, `notion-search`, `notion-update-page` 등

### 2-2. WebFetch / WebSearch — **라이브러리 조사**
- `notebooklm-py` 라이브러리의 최신 API 문서 확인 (PRD 부록 C에서 "최신 문서 참조" 권고)
- GNews API 변경사항 확인
- Flask/Streamlit 패턴 참조

---

## 3. 활용 불가 / 불필요한 Skill

| Skill | 이유 |
|-------|------|
| `keybindings-help` | 키보드 단축키 — 본 프로젝트와 무관 |
| `update-config` | Claude Code 설정 — 본 프로젝트 기능 구현과 무관 |

---

## 4. 추천 활용 순서

| 단계 | Skill/도구 | 용도 |
|------|-----------|------|
| ① 설계/조사 | `WebFetch` | notebooklm-py API 문서, GNews API 최신 사양 확인 |
| ② Claude 연동 구현 | `claude-api` | claude_service.py 작성 시 SDK best practice 적용 |
| ③ Gmail 연동 구현 | Gmail MCP 도구 | 이메일 발송 테스트 및 프로토타이핑 |
| ④ 코드 리뷰 | `simplify` | 각 모듈 완성 후 품질 점검 |
| ⑤ 운영 설정 | `schedule` | Daily 자동 실행 스케줄 설정 (크론 보완) |
| ⑥ 모니터링 | `loop` | 파이프라인 실행 상태 주기적 확인 |
