"""src/prompts.py — Claude 프롬프트 템플릿 관리

reference/runDailyAutomation.js의 프롬프트 원문을 보존하며,
JavaScript 템플릿 리터럴(${var})을 Python .format()으로 변환.
"""


def build_daily_prompt(article_list: str, existing_summaries: str) -> str:
    """Daily 뉴스레터 생성용 프롬프트를 조립한다.

    Args:
        article_list: 수집된 기사 목록 (제목/URL/요약 포맷팅된 문자열)
        existing_summaries: 이전 뉴스레터에 포함된 기사 제목 목록 (중복 배제용)
    """
    return """<role>
당신은 소프트웨어정책연구소(SPRi)의 산업분석 에이전트입니다.
</role>

<main_task>
아래 제공된 기사 목록을 기반으로 글로벌 SW 산업 동향 리포트를 작성하십시오.

<provided_articles>
{article_list}
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
2. 아래 <existing_summaries>에 이미 존재하는 동향과 중복되는 내용은 제외할 것.
3. 일반적인 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례는 제외할 것.
4. 절대로 리포트 본문 외에 부가적 안내 문구를 포함하지 말고 리포트 내용만 출력할 것.
5. 기사는 최대 25개까지만 포함할 것.
</constraints>

<existing_summaries>
{existing_summaries}
</existing_summaries>""".format(
        article_list=article_list,
        existing_summaries=existing_summaries or "(없음)",
    )


def build_weekly_prompt(article_list: str, existing_summaries: str) -> str:
    """Weekly 보고서 생성용 프롬프트를 조립한다.

    Args:
        article_list: 전문가가 선별한 기사 목록
        existing_summaries: 이전 뉴스레터에 포함된 기사 제목 목록 (중복 배제용)
    """
    return """<role>
당신은 소프트웨어정책연구소(SPRi)의 주간 산업분석 에이전트입니다.
</role>

<main_task>
아래 제공된 기사 목록을 기반으로 금주 글로벌 SW 산업 주간 동향 보고서를 작성하십시오.

<provided_articles>
{article_list}
</provided_articles>

<sub_task> 리포트 작성
1. 구성: 다음 6개 섹션을 반드시 포함할 것.
  - ## 1. 개요 : 금주 가장 중요한 3~5가지 핵심 트렌드 요약 및 시사점
  - ## 2. 정책/법제: 글로벌 규제, 표준화, 정부 정책 동향
  - ## 3. 기업/산업: 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
  - ## 4. 인력/교육: 개발자 직무 변화, 신기술 교육, 고용 트렌드
  - ## 5. 기술/연구: 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신
  - ## 6. 하드웨어/인프라: AI 반도체(GPU/NPU/HBM), 데이터센터 아키텍처, 에너지
2. 상세도: 한 주간의 흐름과 맥락을 연결하여 심층 분석할 것. 각 동향 항목은 3문장 이상으로 기술.
3. 스타일: 전문적인 개조식(~임, ~함), SPRi 리포트 톤 유지.
4. 각 동향 항목 첫 줄은 반드시 '**한 줄 요약 문장**' 형식의 볼드 요약으로 시작할 것.
5. 출처: 각 기사 하단에 '* [기사 제목](기사 직접 URL)' 형식으로 기재할 것.
6. 언어: 한국어.
7. 허용 마크다운: '## 섹션명', '**볼드**', '* [제목](URL)' 형식만 사용할 것.
</sub_task>
</main_task>

<constraints>
1. 제공된 기사 목록에서만 선별하여 사용할 것.
2. 아래 <existing_summaries>에 이미 존재하는 동향과 중복되는 내용은 제외할 것.
3. 일반적인 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례는 제외할 것.
4. 절대로 리포트 본문 외에 부가적 안내 문구를 포함하지 말고 리포트 내용만 출력할 것.
5. 기사는 최대 25개까지만 포함할 것.
</constraints>

<existing_summaries>
{existing_summaries}
</existing_summaries>""".format(
        article_list=article_list,
        existing_summaries=existing_summaries or "(없음)",
    )


def format_articles_for_prompt(articles: list[dict]) -> str:
    """기사 목록을 프롬프트에 삽입할 텍스트로 포맷팅한다."""
    lines = []
    for i, a in enumerate(articles, 1):
        lines.append(
            f"{i}. [{a['title']}]({a['url']})\n"
            f"   요약: {a.get('description', 'N/A')}\n"
            f"   출처: {a.get('source_name', 'N/A')} | 발행: {a.get('published_at', 'N/A')}"
        )
    return "\n\n".join(lines)
