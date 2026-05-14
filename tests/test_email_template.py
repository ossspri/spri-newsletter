"""tests/test_email_template.py — HTML 이메일 템플릿 TDD 테스트"""
import pytest

from src.email_template import render_email_html, build_email_subject


SAMPLE_MARKDOWN = """\
## 1. 개요

**AI가 SW 산업 전반을 재편하고 있음**
글로벌 AI 기술이 혁신적 변화를 주도하고 있음.

## 2. 정책/법제

**EU AI Act 시행 준비 본격화**
유럽연합이 AI법 세부 시행 규칙을 확정함.
* [AI Policy Update](https://example.com/policy)"""


class TestRenderEmailHtml:
    def test_daily_title(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일 일요일")
        assert "Daily SW 산업 동향 브리핑" in html

    def test_weekly_title(self):
        html = render_email_html(SAMPLE_MARKDOWN, "weekly", "2026년 3월 29일 일요일")
        assert "주간 SW 산업 동향 보고서" in html

    def test_daily_subtitle(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        assert "DAILY BRIEFING" in html

    def test_weekly_subtitle(self):
        html = render_email_html(SAMPLE_MARKDOWN, "weekly", "2026년 3월 29일")
        assert "WEEKLY REPORT" in html

    def test_date_display(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일 일요일")
        assert "2026년 3월 29일 일요일" in html

    def test_spri_branding_colors(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        assert "#1a2a3a" in html  # 헤더 배경
        assert "#2d5a8e" in html  # 액센트 색상

    def test_gradient_header(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        assert "linear-gradient" in html

    def test_spri_footer(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        assert "소프트웨어정책연구소" in html
        assert "AI 기반으로 자동 생성" in html

    def test_markdown_converted_to_html(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        # ## → <h2>
        assert "<h2" in html
        # **bold** → <strong>
        assert "<strong" in html
        # * [title](url) → <a>
        assert "https://example.com/policy" in html


    def test_no_drive_button_when_no_url(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        assert "구글 문서에서 전문 보기" not in html

    def test_html_structure(self):
        html = render_email_html(SAMPLE_MARKDOWN, "daily", "2026년 3월 29일")
        assert "<!DOCTYPE html>" in html
        assert "<body" in html
        assert "</body>" in html


class TestBuildEmailSubject:
    def test_daily_subject(self):
        subject = build_email_subject("daily", "2026-03-29")
        assert "[Daily]" in subject
        assert "2026-03-29" in subject
        assert "글로벌 SW산업동향" in subject

    def test_weekly_subject(self):
        subject = build_email_subject("weekly", "2026-03-29")
        assert "[Weekly]" in subject
        assert "2026-03-29" in subject
        assert "주간동향" in subject
