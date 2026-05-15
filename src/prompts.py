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
1. 구성: 다음 6개 섹션 헤더를 모두 출력하되, 관련 기사가 있는 섹션만 본문을 작성할 것.
  - ## 1. 개요 : 가장 중요한 3가지 뉴스 요약 및 인사이트
  - ## 2. 정책/법제: 글로벌 규제, 표준화, 정부 정책 동향
  - ## 3. 기업/산업: 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
  - ## 4. 인력/교육: 개발자 직무 변화, 신기술 교육, 고용 트렌드
  - ## 5. 기술/연구: 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신
  - ## 6. 하드웨어/인프라: AI 반도체(GPU/NPU/HBM), 데이터센터 아키텍처, 에너지
  - 관련 기사가 없는 섹션은 헤더만 출력하고 본문에 '_해당 없음 (당일 관련 기사 없음)_' 한 줄만 적을 것. 억지로 기사를 끌어와 채우거나 무관한 내용으로 메우지 말 것.
2. 상세도: 각 동향 항목은 반드시 3문장 이상으로 기술할 것. 단순 헤드라인·사실 나열은 금지.
   각 동향 항목은 다음 3요소를 모두 포함하여 분석할 것:
     (a) 사실(무슨 일이 일어났는가) — 1문장
     (b) 맥락·배경(왜 발생했는가, 관련 숫자·인용) — 1문장 이상
     (c) 산업 구조적 함의(시장 구도/경쟁 지형/정책·인프라 영향, 향후 시그널) — 1문장 이상
3. 스타일: 전문적인 개조식(~임, ~함), SPRi 리포트 톤 유지.
4. 각 동향 항목 첫 줄은 반드시 '**한 줄 요약 문장**' 형식의 볼드 요약으로 시작할 것.
5. 출처: 각 동향 항목의 본문 바로 아래에 '* [기사 제목](기사 직접 URL)' 형식으로 각주처럼 기재할 것. 문서 끝에 출처를 모아놓지 말 것.
6. 언어: 한국어.
7. 허용 마크다운: '## 섹션명', '**볼드**', '_이탤릭_', '* [제목](URL)' 형식만 사용할 것.
</sub_task>

<output_example>
## 2. 정책/법제

**미국 국토안보부의 AI 정책 도입으로 법집행 기관의 AI 활용 가이드라인 정립**
오타와 경찰청이 4월 새로운 AI 정책을 발표할 예정이며...
* [AI is coming to the Ottawa police](https://example.com/article1)

**사진 인증 기술의 보안 취약점 발견으로 디지털 콘텐츠 진위성 검증 표준 재검토 필요**
ETH Zurich 연구진이 Adobe가 주도하는 C2PA 소프트웨어의 해킹 가능성을 제기하며...
* [Researchers Come Up With Foolproof Method](https://example.com/article2)
</output_example>
</main_task>

<constraints>
1. 제공된 기사 목록에서만 선별하여 사용할 것.
2. 아래 <existing_summaries>에 이미 존재하는 동향과 중복되는 내용은 제외할 것.
3. 일반적인 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례는 제외할 것.
4. 절대로 리포트 본문 외에 부가적 안내 문구를 포함하지 말고 리포트 내용만 출력할 것.
5. 기사는 최대 25개까지만 포함할 것.
6. 출처 URL을 문서 끝에 모아놓는 미주 방식은 절대 사용하지 말 것. 반드시 해당 동향 본문 바로 아래에 각주로 배치할 것.
</constraints>

<existing_summaries>
{existing_summaries}
</existing_summaries>""".format(
        article_list=article_list,
        existing_summaries=existing_summaries or "(없음)",
    )


def build_weekly_prompt(article_list: str, existing_summaries: str) -> str:
    """Weekly 표준 주간 보고서 prompt (자동 수집 daily 기사만 입력).

    수동 입력(보고서·전문가 인사이트)과 1차 자료 활용은 ``build_focus_prompt``
    가 담당. Weekly는 단순·표준 형태를 유지하기 위해 옛 시그니처로 복귀.

    구현: ``build_focus_prompt(article_list, existing_summaries)`` 위임 —
    동일 main template이지만 reports/insight 블록은 빈 상태로 prompt에서
    자연스럽게 제외됨. 두 함수의 prompt 본문이 분기되지 않아 유지보수 단순.

    Args:
        article_list: 자동 수집된 daily 기사 7일치 목록
        existing_summaries: 이전 뉴스레터에 포함된 기사 제목 (중복 배제용)
    """
    return build_focus_prompt(article_list, existing_summaries)


def build_focus_prompt(
    article_list: str,
    existing_summaries: str,
    reports: list[dict] | None = None,
    expert_insight: str = "",
) -> str:
    """Focus 큐레이션 보고서 prompt — 자동 수집 + 수동 입력 통합.

    Weekly 표준과 분리된 큐레이션 형태. 2026-05-15 Focus 분리 이전의
    풍부한 build_weekly_prompt 본체를 그대로 이어 받는다.

    Args:
        article_list: 자동 수집 기사 + 사용자 수동 추가 기사 목록 (혼합).
        existing_summaries: 이전 뉴스레터에 포함된 기사 제목 (중복 배제용).
        reports: 사용자가 수동 첨부한 1차 자료(연구보고서/백서/회사 발표).
            None 또는 빈 list면 ``<reports>`` 블록 생략.
        expert_insight: 사용자가 입력한 금주 핵심 인사이트. 비어있으면
            기존 동작. 있으면 ``<expert_insight>`` 블록을 prompt 상단에
            주입하고 LLM이 보고서 ① 개요에 첫 트렌드로 반영하도록 지시.
    """
    if reports:
        report_block = (
            "\n<reports>\n"
            "아래는 전문가가 직접 첨부한 1차 자료(연구보고서/백서/회사 발표)입니다. "
            "이 자료들은 기사보다 신뢰도가 높은 원천이므로 본문에서 직접 인용하고 "
            "출처를 보고서 제목으로 표시하는 것을 우선 고려하십시오. "
            "수치·인용·발표 시점을 가능한 보존하십시오.\n\n"
            + format_reports_for_prompt(reports)
            + "\n</reports>\n"
        )
    else:
        report_block = ""

    if expert_insight and expert_insight.strip():
        insight_block = (
            "\n<expert_insight>\n"
            "아래는 SPRi 전문가가 직접 작성한 금주 핵심 인사이트입니다. "
            "본 보고서 작성 시 이 인사이트를 다음과 같이 반영하십시오:\n"
            "  1. 보고서의 '## 1. 개요' 섹션에 이 인사이트를 첫 트렌드로 명확히 반영할 것.\n"
            "  2. 제공된 기사·보고서 중 이 인사이트와 직접 관련된 것을 식별하고, 해당 "
            "자료의 본문 요약을 인사이트 맥락으로 재해석·증강하여 작성할 것. 단순 "
            "요약이 아니라, 인사이트와 어떻게 연결되는지가 드러나도록 분석할 것.\n"
            "  3. 인사이트와 무관한 자료도 그대로 다른 섹션에 반영하되, 본 인사이트가 "
            "보고서 전체 톤을 결정하는 가장 중요한 메시지임을 인식할 것.\n\n"
            + expert_insight.strip()
            + "\n</expert_insight>\n"
        )
    else:
        insight_block = ""

    return """<role>
당신은 소프트웨어정책연구소(SPRi)의 주간 산업분석 에이전트입니다.
</role>
{insight_block}
<main_task>
아래 제공된 기사 목록을 기반으로 금주 글로벌 SW 산업 주간 동향 보고서를 작성하십시오.

<provided_articles>
{article_list}
</provided_articles>
{report_block}

<sub_task> 리포트 작성
1. 구성: 다음 6개 섹션 헤더를 모두 출력하되, 관련 기사가 있는 섹션만 본문을 작성할 것.
  - ## 1. 개요 : 금주 가장 중요한 3~5가지 핵심 트렌드 요약 및 시사점
  - ## 2. 정책/법제: 글로벌 규제, 표준화, 정부 정책 동향
  - ## 3. 기업/산업: 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
  - ## 4. 인력/교육: 개발자 직무 변화, 신기술 교육, 고용 트렌드
  - ## 5. 기술/연구: 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신
  - ## 6. 하드웨어/인프라: AI 반도체(GPU/NPU/HBM), 데이터센터 아키텍처, 에너지
  - 관련 기사가 없는 섹션은 헤더만 출력하고 본문에 '_해당 없음 (금주 관련 기사 없음)_' 한 줄만 적을 것. 억지로 기사를 끌어와 채우거나 무관한 내용으로 메우지 말 것.
2. 상세도: 한 주간의 흐름과 맥락을 연결하여 심층 분석할 것. 각 동향 항목은 반드시 3문장 이상으로 기술하고, 단순 헤드라인·사실 나열은 금지.
   각 동향 항목은 다음 3요소를 모두 포함하여 분석할 것:
     (a) 사실(무슨 일이 일어났는가) — 1문장
     (b) 맥락·배경(주중 누적된 흐름, 관련 숫자·인용) — 1문장 이상
     (c) 산업 구조적 함의(시장 구도/경쟁 지형/정책·인프라 영향, 향후 시그널) — 1문장 이상
3. 스타일: 전문적인 개조식(~임, ~함), SPRi 리포트 톤 유지.
4. 각 동향 항목 첫 줄은 반드시 '**한 줄 요약 문장**' 형식의 볼드 요약으로 시작할 것.
5. 출처: 각 동향 항목의 본문 바로 아래에 '* [기사 제목](기사 직접 URL)' 형식으로 각주처럼 기재할 것. 문서 끝에 출처를 모아놓지 말 것.
6. 언어: 한국어.
7. 허용 마크다운: '## 섹션명', '**볼드**', '_이탤릭_', '* [제목](URL)' 형식만 사용할 것.
</sub_task>

<output_example>
## 2. 정책/법제

**미국 국토안보부의 AI 정책 도입으로 법집행 기관의 AI 활용 가이드라인 정립**
오타와 경찰청이 4월 새로운 AI 정책을 발표할 예정이며...
* [AI is coming to the Ottawa police](https://example.com/article1)

**사진 인증 기술의 보안 취약점 발견으로 디지털 콘텐츠 진위성 검증 표준 재검토 필요**
ETH Zurich 연구진이 Adobe가 주도하는 C2PA 소프트웨어의 해킹 가능성을 제기하며...
* [Researchers Come Up With Foolproof Method](https://example.com/article2)
</output_example>
</main_task>

<constraints>
1. 제공된 기사 목록 + (있다면) <reports> 1차 자료에서만 선별하여 사용할 것.
2. 아래 <existing_summaries>에 이미 존재하는 동향과 중복되는 내용은 제외할 것.
3. 일반적인 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례는 제외할 것.
4. 절대로 리포트 본문 외에 부가적 안내 문구를 포함하지 말고 리포트 내용만 출력할 것.
5. 기사는 최대 25개까지만 포함할 것.
6. 출처 URL을 문서 끝에 모아놓는 미주 방식은 절대 사용하지 말 것. 반드시 해당 동향 본문 바로 아래에 각주로 배치할 것.
7. <reports>에 첨부된 1차 자료가 있으면 동향 본문에 가능한 직접 인용하고, 출처는 '* 보고서: {{title}}' 형태로 본문 아래에 표시할 것.
</constraints>

<existing_summaries>
{existing_summaries}
</existing_summaries>""".format(
        article_list=article_list,
        existing_summaries=existing_summaries or "(없음)",
        report_block=report_block,
        insight_block=insight_block,
    )


def build_postprocess_prompt(raw_report: str) -> str:
    """이미 작성된 industry-scan 분석 보고서를 일간 뉴스레터 6섹션 포맷으로
    재구성하는 프롬프트를 조립한다.

    `build_daily_prompt()`의 출력 형식 가이드(6섹션·3요소 분석·출처 각주·
    허용 마크다운)를 차용하되, 입력이 raw articles가 아니라 이미 작성된
    분석 보고서임을 명시한다.

    **출처 100% 보존이 최우선**. 분량은 평가 대상이 아니므로 압축 강요
    없음. 결과 분량은 출처를 모두 포함한 자연스러운 길이로 결정된다.

    Args:
        raw_report: industry-scan 4-Pass가 생성한 풍부한 분석 보고서 (마크다운)
    """
    return """<role>
당신은 소프트웨어정책연구소(SPRi)의 산업분석 에이전트입니다.
이미 작성된 풍부한 SW 산업 동향 분석 보고서를 일간 뉴스레터 형식으로
재구성하는 편집 작업을 수행합니다.
</role>

<main_task>
아래 <input_report>에 담긴 분석 내용을 SPRi 일간 뉴스레터 6섹션 포맷으로
재구성하십시오. 출력 형식만 단순하고 가독성 높은 일간 뉴스레터 스타일로
변환하되, **입력 보고서의 모든 출처는 한 건도 빠짐없이 100% 보존**해야 합니다.

<input_report>
{raw_report}
</input_report>

<sub_task> 보고서 재구성
1. 구성: 다음 6개 섹션 헤더를 모두 출력하되, 관련 내용이 있는 섹션만 본문을 작성할 것.
  - ## 1. 개요 : 가장 중요한 3가지 트렌드 요약 및 인사이트
  - ## 2. 정책/법제: 글로벌 규제, 표준화, 정부 정책 동향
  - ## 3. 기업/산업: 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
  - ## 4. 인력/교육: 개발자 직무 변화, 신기술 교육, 고용 트렌드
  - ## 5. 기술/연구: 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신
  - ## 6. 하드웨어/인프라: AI 반도체(GPU/NPU/HBM), 데이터센터 아키텍처, 에너지
  - 입력 보고서에 관련 내용이 없는 섹션은 헤더만 출력하고 본문에 '_해당 없음 (입력 보고서에 관련 내용 없음)_' 한 줄만 적을 것. 억지로 끌어와 채우거나 무관한 내용으로 메우지 말 것.
2. 상세도: 각 동향 항목은 반드시 3문장 이상으로 기술할 것. 단순 헤드라인·사실 나열은 금지.
   각 동향 항목은 다음 3요소를 모두 포함하여 분석할 것:
     (a) 사실(무슨 일이 일어났는가) — 1문장
     (b) 맥락·배경(관련 숫자·인용·산업 흐름) — 1문장 이상
     (c) 산업 구조적 함의(시장 구도/경쟁 지형/정책·인프라 영향, 향후 시그널) — 1문장 이상
3. 스타일: 전문적인 개조식(~임, ~함), SPRi 리포트 톤 유지.
4. 각 동향 항목 첫 줄은 반드시 '**한 줄 요약 문장**' 형식의 볼드 요약으로 시작할 것.
5. 출처: 각 동향 항목의 본문 바로 아래에 '* [기사 제목](기사 직접 URL)' 형식으로 각주처럼 기재할 것. 문서 끝에 출처를 모아놓지 말 것.
6. 언어: 한국어.
7. 허용 마크다운: '## 섹션명', '**볼드**', '_이탤릭_', '* [제목](URL)' 형식만 사용할 것.
   '###', '####' 등 3단계 이상 헤더는 절대 사용하지 말 것.
</sub_task>

<output_example>
## 2. 정책/법제

**미국 국토안보부의 AI 정책 도입으로 법집행 기관의 AI 활용 가이드라인 정립**
오타와 경찰청이 4월 새로운 AI 정책을 발표할 예정이며, 이는 법집행에서의 AI 활용 기준을 명확히 하는 신호임. 이번 정책은 캐나다 내 다른 공공기관의 AI 도입 가이드라인 확산을 가속화할 가능성이 큼. SW 정책 관점에서 보면, 공공 부문 AI 도입 표준이 국가별로 분기되는 흐름의 일환으로 해석됨.
* [AI is coming to the Ottawa police](https://example.com/article1)
</output_example>
</main_task>

<source_preservation_rule priority="HIGHEST">
입력 보고서(<input_report>)에 등장한 모든 출처('* [제목](URL)' 형식)를
한 건도 빠짐없이 100% 보존하라. **출처 누락은 본 작업의 명백한 실패다.**

- 분량 압축은 분석 텍스트만 대상으로 한다. 출처 링크 자체는 절대 압축·생략·통합하지 말 것.
- 동일 출처가 여러 동향에서 인용된다면, 각 위치에 모두 보존할 것 (한 곳만 남기지 말 것).
- 입력 보고서의 어떤 부록·메타정보 안에 들어있던 출처라도 본 출력의 적절한 동향 항목 아래에 반드시 재배치할 것.
- 분량이 길어지더라도 출처를 절대 빼지 말 것. 분량은 평가 대상이 아님.

**최종 출력을 내기 전에 자체 검증하라:**
1. 입력 보고서의 모든 '* [제목](URL)' 출처 개수를 세라.
2. 출력에 포함된 '* [제목](URL)' 출처 개수가 그와 같거나 더 많은지 확인하라.
3. 같지 않다면 누락된 출처를 찾아 적절한 동향 항목 아래에 추가한 뒤 출력하라.
</source_preservation_rule>

<constraints>
1. 입력 보고서(<input_report>)에 명시된 분석 내용·수치·출처만 사용할 것. 새로운 정보를 추가하지 말 것.
2. 입력 보고서의 부록(데이터 수집 요약·메타정보·검증 결과 등) 본문은 출력에서 제거하되, 그 안에 들어있던 출처는 위 source_preservation_rule에 따라 본문 동향에 재배치할 것.
3. **분량 목표 없음.** 출처를 모두 보존한 자연스러운 길이로 작성. 길어져도 무방.
4. 절대로 리포트 본문 외에 부가적 안내 문구를 포함하지 말고 리포트 내용만 출력할 것.
5. 출처 URL을 문서 끝에 모아놓는 미주 방식은 절대 사용하지 말 것. 반드시 해당 동향 본문 바로 아래에 각주로 배치할 것.
6. 4단계 이상 마크다운 헤더('###', '####')는 절대 사용하지 말 것. 섹션 구조는 '## 1. ~ ## 6.'만 허용.
</constraints>""".format(
        raw_report=raw_report,
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


def format_reports_for_prompt(reports: list[dict], max_excerpt_chars: int = 4000) -> str:
    """수동 첨부 1차 자료(보고서)를 프롬프트에 삽입할 텍스트로 포맷팅.

    Args:
        reports: ``get_manual_report`` 또는 ``get_all_manual_reports``의 dict
            list. 기대 키: ``title``, ``url``, ``original_filename``,
            ``summary``, 추가로 ``head_excerpt``가 있으면 함께 포함.
        max_excerpt_chars: 보고서 1건당 발췌 길이 상한 (토큰 통제).

    Returns:
        ``[보고서 N] 제목 / 출처 / 요약 / 핵심 발췌`` 블록을 ``---``로
        구분한 단일 문자열.
    """
    if not reports:
        return ""

    blocks = []
    for i, r in enumerate(reports, 1):
        title = r.get("title", "(제목 없음)")
        url = r.get("url", "")
        original = r.get("original_filename", "")
        summary = (r.get("summary") or "").strip()
        excerpt = (r.get("head_excerpt") or "").strip()[:max_excerpt_chars]

        if url:
            source_line = f"출처: {url}"
        elif original:
            source_line = f"출처: PDF 업로드 (원본 파일: {original})"
        else:
            source_line = "출처: 수동 첨부"

        block = f"[보고서 {i}] {title}\n{source_line}"
        if summary:
            block += f"\n요약: {summary}"
        if excerpt:
            block += f"\n\n핵심 발췌:\n{excerpt}"
        blocks.append(block)

    return "\n\n---\n\n".join(blocks)
