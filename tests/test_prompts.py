"""tests/test_prompts.py — 프롬프트 템플릿 TDD 테스트"""
import pytest

from src.prompts import (
    build_daily_prompt,
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
