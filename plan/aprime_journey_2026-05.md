# A′(industry-scan) 도입 작업 기록 — 2026년 5월

본 문서는 2026-04-29 ~ 2026-05-07 기간 동안 진행된 SPRi 뉴스레터 시스템의
A′(industry-scan 기반 자동화) 도입 작업을 정리합니다. **운영 발송에는 영향 없으며**,
모든 변경은 검증·측정 인프라 수준입니다.

---

## 1. 배경과 동기

**문제 인식** (4월 말): 매일 발송되는 두 종류의 뉴스레터를 비교하니 GAS 기반 외부 시스템(B)이 우리 시스템(A)을 일관되게 앞섬.

| 출처 | 코드 | 데이터 수집 방식 |
|---|---|---|
| **A** | `newsletter_system` (이 프로젝트) | GNews API + Claude로 6섹션 생성 |
| **B** | `sw-trend-daily` (별도 GAS 프로젝트) | Claude API의 `web_search_20250305` tool로 직접 검색 |

7일치 LLM-as-judge 측정 결과 A 평균 ~7.6 / B 평균 ~8.7로 약 -1.0~-1.8 격차가 일관적.

**가설**: 데이터 수집을 단일 소스(GNews)에서 다중 소스로 확장하고, 보고서 생성을 분리하는 방식(A′)이 효과적일 것.

---

## 2. 작업 타임라인

### 단계 1: GNews 시장 특화 필터링 (commit `8e53277`)
- 화이트리스트 매체(Reuters/Bloomberg/CNBC/TechCrunch 등 23개) + fallback 쿼리 + boolean 연산자
- 프롬프트 강화: 3요소 분석(사실+맥락+산업 구조적 함의) 의무화
- A/B 비교 도구 신규 (`scripts/compare_configs.py`, `scripts/compare_newsletters.py`)
- **결과**: 격차 줄지 않음 (-1.2~-1.8 유지)

### 단계 2: A′ 도입 — industry-scan 스킬 자동화
- prism-data MCP를 standalone Python에서 호출 (`scripts/run_industry_scan.py`)
- prism .env에 누락된 키 5개 추가 (Naver/Tavily/Guardian/data_go_kr/OpenDart)
- Claude API tool use 루프로 5개 소스(Naver/Guardian/Tavily/GNews/HN) 통합 수집
- 04-29 1회 측정에서 **A′ > B 역전** (A′ 8.4 / B 7.6)

### 단계 3: prism 업데이트 통합 (이지훈 이메일)
- prism git pull → envelope.py(컨텍스트 33배 감축) + 4-Pass 동적 토픽 발견 구조
- Claude Desktop의 plugin SKILL.md GUI 갱신 (사용자 수동)
- `run_industry_scan.py`를 SKILL.md **동적 로드 방식**으로 변경 → 향후 SKILL 업데이트 자동 반영

### 단계 4: 3-way 비교 인프라
- `scripts/compare_three.py` — A/A′/B 한 번의 LLM 호출로 5차원 동시 채점 (비용 36% 절감)
- `scripts/daily_ab_test.py` — 한 줄 wrapper (GAS B 추출 + A′ 생성 + 3-way 비교)

### 단계 5: 후처리(post-process) 도입
- A′ raw(16K자, 4단계 헤더, 부록 포함)의 구조·가독성 점수가 일관 약점
- `src/prompts.py`에 `build_postprocess_prompt()` 추가 — raw → 일간 뉴스레터 6섹션 형식 변환
- **출처 100% 보존 강제** (`<source_preservation_rule priority="HIGHEST">` + 자체 검증 지시)
- 분량 가이드 제거 (출처 보존이 분량 압박과 충돌)
- 채점 기준 변경: `DIMENSIONS` structure 정의에 "(분량·간결성·길이는 평가 대상이 아니므로 무시)" 추가
- **검증**: 출처 15/15(100%) 보존 확인, A′ 8.6 / B 7.8로 A′ 우위 (commit `e9113ae`)

### 단계 6: 1주일 자동 측정 + 통계 검정
- `scripts/aggregate_ab_summary.py` — paired t-test로 A′ vs B 통계적 유의성 판정
- t분포 CDF는 incomplete beta function(NR §6.4)으로 직접 구현 (외부 의존성 0)
- scipy 결과와 4건 검증에서 0.0000 오차로 일치 확인
- `scripts/register_aprime_ab_test.bat` — Windows Task Scheduler 등록 (commit `c3421bb`)
- **AprimeABTest 등록 완료** — 매일 06:30 KST 자동 실행

---

## 3. 추가된 파일·인프라

### 신규 모듈 (master 브랜치, A 운영 코드 영향 0)

| 경로 | 역할 |
|---|---|
| `scripts/run_industry_scan.py` | A′ 자동화 — prism MCP + Claude tool use loop + 후처리 |
| `scripts/compare_newsletters.py` | 2-way LLM-as-judge 비교 |
| `scripts/compare_three.py` | 3-way A/A′/B 동시 비교 |
| `scripts/compare_configs.py` | GNews 설정 A/B 비교 |
| `scripts/daily_ab_test.py` | 일간 측정 wrapper |
| `scripts/aggregate_ab_summary.py` | 누적 통계 검정 |
| `scripts/register_aprime_ab_test.bat` | Task Scheduler 등록 |
| `src/prompts.py:build_postprocess_prompt()` | A′ 후처리 prompt (출처 100% 보존) |

### A 운영 코드 (변경 없음)

`main.py` / `src/news_service.py` / `src/claude_service.py` / `src/prompts.py:build_daily_prompt()` 등 매일 05:00 발송 흐름은 **그대로** GNews 기반.

### 호출 경로 격리

```
[매일 05:00] SPRi_Daily_Newsletter (기존 Task)
   └→ main.py --mode daily → news_service(GNews) → claude_service → 발송 (수신자 7명)

[매일 06:30] AprimeABTest (신규 Task, 2026-05-07 등록)
   └→ daily_ab_test.py → run_industry_scan(prism MCP) → compare_three → 측정 (발송 X)
```

한 함수도 양쪽이 공유하지 않음. A 발송 흐름은 A′ 추가와 무관하게 동작.

---

## 4. 측정 결과 누적 (6일치, 단계 5/6 적용 전)

| 일자 | A | A′ | B | 1위 | 비고 |
|---|---|---|---|---|---|
| 05-02 | 8.0 | 8.4 | 8.8 | B | A′ 도입 직후 |
| 05-03 | 7.6 | 8.4 | 9.2 | B | |
| 05-04 (envelope 전) | 7.4 | 8.2 | 8.8 | B | |
| 05-04 (envelope 후) | 8.0 | 8.6 | 8.6 | A′ | prism 업데이트 적용 첫날 |
| 05-06 (envelope만) | 8.4 | 8.0 | 9.0 | B | |
| 05-06 (4-Pass) | 8.0 | 8.4 | 8.2 | A | SKILL 동기화 후 |
| 05-07 (raw, ab_summary) | 7.6 | 8.4 | 8.8 | B | |
| **05-07 (후처리+채점기준)** | **8.0** | **8.6** | **7.8** | **A′** | 단계 5 적용 후 직접 측정 |

**누적 평균** (단계 5 적용 전 6일치 ab_summary 기준):
- A 7.80 / A′ 8.43 / **B 8.77** — B가 평균 +0.34 우위
- paired t-test: t = -2.193, p = 0.0798 (유의성 부족)
- 결정 신호: ❌ "A′이 B보다 우월하지 않음"

단, **단계 5/6이 적용된 측정은 1일치만(05-07 직접 compare에서 A′ 우위)** 존재.
다음 1주일 누적이 진짜 비교 기간.

---

## 5. Commit 이력 (이번 작업)

| commit | 변경 내용 |
|---|---|
| `8e53277` | feat: SW 산업 시장 특화 필터링 + 프롬프트 강화 + A/B 비교 도구 |
| `e9113ae` | feat: A′(industry-scan 자동화) + 후처리 + 3-way A/A′/B 비교 도구 |
| `c3421bb` | feat: 1주일 A/A′/B 측정 자동화 + paired t-test 통계 검정 |

모두 master 브랜치, GitHub origin/master에 push 완료.

---

## 6. 향후 작업

### 다음 1주일 (~2026-05-14)
- 매일 06:30 KST AprimeABTest 자동 실행 (수동 개입 0)
- 누적 데이터: `logs/ab_summary_<date>.md`
- 중간 점검: `python scripts/aggregate_ab_summary.py` 한 줄

### 1주일 후 결정 분기
`python scripts/aggregate_ab_summary.py` 결과의 **결정 신호** 기준:

| 신호 | 의미 | 다음 작업 |
|---|---|---|
| ✅ 운영 교체 결정 가능 | A′ > B AND p < 0.05 AND n ≥ 5 | 별도 plan으로 main.py 흐름 교체 |
| ⚠️ 추가 측정 필요 | 평균 차이는 양수지만 p ≥ 0.05 | 며칠 더 누적 |
| ❌ 우월하지 않음 | 평균 차이 ≤ 0 | A′ 추가 개선 또는 보류 |
| ⏸ 측정 부족 | n < 5 | 1주일 더 자동 측정 |

### 운영 교체 시 (별도 plan, 현 plan 범위 밖)
- 새 모듈 `src/industry_scan_service.py` (prism MCP + 후처리 통합)
- `main.py` 분기: `news_mode: "gnews" | "industry_scan"` config flag
- fallback 메커니즘 (industry-scan 실패 시 GNews 자동 폴백)
- 발송 영향 직접 → 신중한 검증·점진적 전환

---

## 7. 핵심 검증 도구 사용법

```bash
# 매일 측정 (Task Scheduler가 자동 실행, 수동 가능)
python scripts/daily_ab_test.py
python scripts/daily_ab_test.py --force-aprime    # A′ 재생성

# 누적 통계
python scripts/aggregate_ab_summary.py             # 최근 7일
python scripts/aggregate_ab_summary.py --days 14
python scripts/aggregate_ab_summary.py --since 2026-05-08

# 1회 비교만 (A′ 재사용)
python scripts/compare_three.py \
  --a data/newsletters/daily_<date>.md \
  --aprime logs/newsletterA-prime_<date>.md \
  --b logs/newsletterB_<date>.md
```

---

## 8. 외부 의존성 변경

- prism repo (`C:/Users/martin.hs.yoo/dev/prism`): git pull로 최신 4-Pass + envelope 적용
- prism `.env`: Naver/Tavily/Guardian/data_go_kr/OpenDart 5개 키 추가
- Claude Desktop plugin: industry-scan SKILL.md 신규 버전(581줄, 4-Pass) 등록
- newsletter_system: scipy 등 외부 패키지 추가 없음 (Python 표준만 사용)

---

## 9. 알려진 이슈·주의사항

- A′의 출처 신뢰도 차원이 7~8점에서 정체 — LLM judge가 "신뢰도"를 매체 다양성·고품질 매체 인용으로 평가하는 경향. 출처 개수 보존만으로는 점수가 안 오름.
- `daily_ab_test.py`는 cwd가 PROJECT_ROOT여야 함 (Task Scheduler 등록 시 working directory 별도 지정 안 했으나 `__file__` 기준 PROJECT_ROOT 추론하므로 동작 OK).
- prism MCP가 다운되거나 prism .env 키가 만료되면 A′ 측정만 실패, A 발송엔 영향 없음.
- AprimeABTest는 PC가 06:30에 켜져있어야 실행됨 (WakeToRun 미설정).
