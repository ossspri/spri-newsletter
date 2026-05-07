"""tests/test_prompts.py — 프롬프트 템플릿 TDD 테스트"""
import pytest

from src.prompts import (
    build_daily_prompt,
    build_postprocess_prompt,
    build_weekly_prompt,
    format_articles_for_prompt,
)


SAMPLE_ARTICLES = [
    {
        "title": "AI Revolution in Software",
        "url": "https://example.com/article1",
        "description": "AI is transforming the software industry",
        "source_name": "TechNews",
        "published_at": "2026-03-29T10:00:00Z",
    },
    {
        "title": "GPU Demand Surges",
        "url": "https://example.com/article2",
        "description": "GPU market sees unprecedented growth",
        "source_name": "HardwareWeekly",
        "published_at": "2026-03-29T08:00:00Z",
    },
]


class TestFormatArticles:
    def test_numbered_list(self):
        result = format_articles_for_prompt(SAMPLE_ARTICLES)
        assert "1. [AI Revolution in Software]" in result
        assert "2. [GPU Demand Surges]" in result

    def test_url_included(self):
        result = format_articles_for_prompt(SAMPLE_ARTICLES)
        assert "https://example.com/article1" in result
        assert "https://example.com/article2" in result

    def test_description_included(self):
        result = format_articles_for_prompt(SAMPLE_ARTICLES)
        assert "AI is transforming" in result

    def test_source_and_date(self):
        result = format_articles_for_prompt(SAMPLE_ARTICLES)
        assert "TechNews" in result
        assert "2026-03-29T10:00:00Z" in result

    def test_empty_list(self):
        result = format_articles_for_prompt([])
        assert result == ""

    def test_missing_optional_fields(self):
        articles = [{"title": "Test", "url": "https://test.com", "published_at": "2026-03-29"}]
        result = format_articles_for_prompt(articles)
        assert "N/A" in result  # description missing


class TestBuildDailyPrompt:
    def test_contains_role(self):
        prompt = build_daily_prompt("articles here", "summaries here")
        assert "소프트웨어정책연구소(SPRi)의 산업분석 에이전트" in prompt

    def test_articles_injected(self):
        prompt = build_daily_prompt("TEST_ARTICLE_LIST", "")
        assert "TEST_ARTICLE_LIST" in prompt

    def test_existing_summaries_injected(self):
        prompt = build_daily_prompt("articles", "PREV_SUMMARY_1\nPREV_SUMMARY_2")
        assert "PREV_SUMMARY_1" in prompt
        assert "PREV_SUMMARY_2" in prompt

    def test_empty_summaries_fallback(self):
        prompt = build_daily_prompt("articles", "")
        assert "(없음)" in prompt

    def test_six_sections_mentioned(self):
        prompt = build_daily_prompt("articles", "")
        assert "## 1. 개요" in prompt
        assert "## 2. 정책/법제" in prompt
        assert "## 3. 기업/산업" in prompt
        assert "## 4. 인력/교육" in prompt
        assert "## 5. 기술/연구" in prompt
        assert "## 6. 하드웨어/인프라" in prompt

    def test_constraints_present(self):
        prompt = build_daily_prompt("articles", "")
        assert "제공된 기사 목록에서만" in prompt
        assert "최대 25개" in prompt
        assert "리포트 본문 외에" in prompt

    def test_daily_not_weekly(self):
        """Daily 프롬프트에 '주간' 키워드가 없어야 한다."""
        prompt = build_daily_prompt("articles", "")
        assert "주간 산업분석" not in prompt


class TestBuildWeeklyPrompt:
    def test_contains_weekly_role(self):
        prompt = build_weekly_prompt("articles", "")
        assert "주간 산업분석 에이전트" in prompt

    def test_weekly_overview_description(self):
        prompt = build_weekly_prompt("articles", "")
        assert "3~5가지 핵심 트렌드" in prompt

    def test_depth_instruction(self):
        prompt = build_weekly_prompt("articles", "")
        assert "한 주간의 흐름과 맥락" in prompt

    def test_articles_injected(self):
        prompt = build_weekly_prompt("WEEKLY_ARTICLES", "")
        assert "WEEKLY_ARTICLES" in prompt

    def test_summaries_injected(self):
        prompt = build_weekly_prompt("articles", "EXISTING")
        assert "EXISTING" in prompt

    def test_six_sections_mentioned(self):
        prompt = build_weekly_prompt("articles", "")
        assert "## 1. 개요" in prompt
        assert "## 6. 하드웨어/인프라" in prompt


class TestBuildPostprocessPrompt:
    def test_raw_report_injected(self):
        prompt = build_postprocess_prompt("RAW_REPORT_CONTENT_HERE")
        assert "RAW_REPORT_CONTENT_HERE" in prompt

    def test_six_sections_mentioned(self):
        prompt = build_postprocess_prompt("body")
        assert "## 1. 개요" in prompt
        assert "## 2. 정책/법제" in prompt
        assert "## 3. 기업/산업" in prompt
        assert "## 4. 인력/교육" in prompt
        assert "## 5. 기술/연구" in prompt
        assert "## 6. 하드웨어/인프라" in prompt

    def test_postprocess_role(self):
        prompt = build_postprocess_prompt("body")
        # 후처리 역할 명시 (편집/재구성)
        assert "재구성" in prompt or "압축" in prompt

    def test_3_element_analysis(self):
        prompt = build_postprocess_prompt("body")
        # build_daily_prompt와 일관된 3요소 분석 의무
        assert "사실" in prompt
        assert "맥락" in prompt
        assert "함의" in prompt

    def test_no_length_target(self):
        prompt = build_postprocess_prompt("body")
        # 분량 목표 제거 검증 — 8000/10000 같은 압축 숫자가 없어야 함
        assert "8,000" not in prompt and "8000" not in prompt
        assert "10,000" not in prompt and "10000" not in prompt
        # "분량 목표 없음" 또는 "길어져도 무방" 같은 명시 표현
        assert "분량 목표 없음" in prompt or "길어져도" in prompt

    def test_strict_source_preservation(self):
        prompt = build_postprocess_prompt("body")
        # 출처 100% 보존 강제 표현
        assert "100%" in prompt
        assert "한 건도 빠짐없이" in prompt
        assert "명백한 실패" in prompt

    def test_self_verification_instruction(self):
        prompt = build_postprocess_prompt("body")
        # 출력 전 자체 검증 지시
        assert "자체 검증" in prompt or "최종 출력" in prompt
        # 출처 개수 비교 지시
        assert "개수" in prompt

    def test_forbid_deep_headers(self):
        prompt = build_postprocess_prompt("body")
        # 4단계 이상 헤더 금지 명시 (구조/가독성 개선의 핵심)
        assert "####" in prompt or "3단계 이상 헤더" in prompt or "4단계 이상" in prompt

    def test_appendix_removal(self):
        prompt = build_postprocess_prompt("body")
        # 부록·메타정보 제거 명시
        assert "부록" in prompt

    def test_no_existing_summaries_arg(self):
        # build_daily_prompt와 달리 existing_summaries 인자 없음
        # → 시그니처 검증: 인자 1개만 받음
        import inspect
        sig = inspect.signature(build_postprocess_prompt)
        assert len(sig.parameters) == 1
        assert "raw_report" in sig.parameters

    def test_input_report_tag(self):
        prompt = build_postprocess_prompt("INNER_BODY")
        # 입력이 <input_report> 태그로 감싸져 들어가는지
        assert "<input_report>" in prompt
        assert "INNER_BODY" in prompt

    def test_only_report_body_output(self):
        prompt = build_postprocess_prompt("body")
        # 부가 안내문 금지 (build_daily_prompt와 일관)
        assert "리포트 본문 외에" in prompt or "다른 텍스트" in prompt or "안내 문구를 포함하지" in prompt
