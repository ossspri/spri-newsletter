"""tests/test_utils.py — 유틸리티 모듈 TDD 테스트"""
import time
from unittest.mock import MagicMock

import pytest

from src.utils import (
    retry,
    get_kst_now,
    get_kst_date_str,
    get_kst_24h_ago_utc,
    get_week_monday_str,
    markdown_to_html,
)


# ── retry 데코레이터 ──

class TestRetry:
    def test_success_on_first_try(self):
        call_count = 0

        @retry(max_retries=3, delay=0)
        def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count == 1

    def test_success_after_retries(self):
        call_count = 0

        @retry(max_retries=3, delay=0)
        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("network error")
            return "ok"

        result = fail_then_succeed()
        assert result == "ok"
        assert call_count == 3

    def test_raise_after_max_retries(self):
        @retry(max_retries=2, delay=0)
        def always_fail():
            raise ConnectionError("network error")

        with pytest.raises(ConnectionError):
            always_fail()

    def test_delay_between_retries(self):
        call_count = 0

        @retry(max_retries=2, delay=0.1)
        def fail_once():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            return "ok"

        start = time.time()
        fail_once()
        elapsed = time.time() - start
        assert elapsed >= 0.1


# ── KST 날짜 헬퍼 ──

class TestKSTHelpers:
    def test_get_kst_now_returns_string(self):
        result = get_kst_now()
        assert isinstance(result, str)
        # YYYY-MM-DDTHH:MM:SS 형식
        assert "T" in result
        assert len(result) >= 19

    def test_get_kst_date_str_format(self):
        result = get_kst_date_str()
        # YYYY-MM-DD
        parts = result.split("-")
        assert len(parts) == 3
        assert len(parts[0]) == 4

    def test_get_kst_24h_ago_utc(self):
        result = get_kst_24h_ago_utc()
        # ISO 8601 UTC 형식
        assert result.endswith("Z") or "+" in result or "T" in result

    def test_get_week_monday_str(self):
        # 2026-03-29 (일요일) → 월요일은 2026-03-23
        result = get_week_monday_str("2026-03-29")
        assert result == "0323"

    def test_get_week_monday_str_monday(self):
        # 2026-03-30 (월요일) → 자기 자신
        result = get_week_monday_str("2026-03-30")
        assert result == "0330"


# ── 마크다운 → HTML 변환 ──

class TestMarkdownToHtml:
    def test_h2_conversion(self):
        md = "## 1. 개요"
        html = markdown_to_html(md)
        assert "<h2" in html
        assert "1. 개요" in html
        assert "#1a2a3a" in html  # PRD 색상

    def test_bold_conversion(self):
        md = "**AI 혁명이 SW 산업 변화를 가속화**"
        html = markdown_to_html(md)
        assert "<strong" in html
        assert "AI 혁명이 SW 산업 변화를 가속화" in html

    def test_source_link_conversion(self):
        md = "* [Tech Article](https://example.com/article)"
        html = markdown_to_html(md)
        assert "<a href" in html
        assert "https://example.com/article" in html
        assert "Tech Article" in html

    def test_inline_link_conversion(self):
        md = "자세한 내용은 [여기](https://example.com)를 참조"
        html = markdown_to_html(md)
        assert '<a href="https://example.com"' in html

    def test_hr_conversion(self):
        md = "---"
        html = markdown_to_html(md)
        assert "<hr" in html

    def test_newline_to_br(self):
        md = "line1\nline2"
        html = markdown_to_html(md)
        assert "<br>" in html

    def test_no_br_after_block_elements(self):
        md = "## Section\nText"
        html = markdown_to_html(md)
        # </h2> 뒤에 바로 <br>이 오면 안 됨
        assert "</h2><br>" not in html

    def test_combined_markdown(self):
        md = """## 1. 개요

**AI 기업들의 대규모 투자가 이어지고 있음**
글로벌 빅테크 기업들이 AI 분야에 수조 원 규모의 투자를 단행하고 있음.
* [AI Investment Surge](https://example.com/ai-invest)

## 2. 정책/법제

**EU AI Act 시행이 본격화됨**
유럽연합의 AI 규제법이 2026년부터 본격 시행에 들어감.
* [EU AI Act](https://example.com/eu-ai-act)"""

        html = markdown_to_html(md)
        assert html.count("<h2") == 2
        assert html.count("<strong") >= 2
        assert html.count("<a href") >= 2

    def test_prd_colors_used(self):
        md = "## Section\n* [Link](https://example.com)"
        html = markdown_to_html(md)
        # PRD 색상: #1a2a3a, #2d5a8e
        assert "#2d5a8e" in html
