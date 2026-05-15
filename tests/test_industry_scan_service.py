"""tests/test_industry_scan_service.py — A'(industry-scan) 운영 서비스 단위 테스트.

scripts.run_industry_scan.run() + postprocess_to_daily_format()을 mock해
IndustryScanService.generate()의 분기·에러 처리를 검증.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.industry_scan_service import (
    IndustryScanService, IndustryScanError, extract_article_urls,
)


# ── extract_article_urls ──


class TestExtractArticleUrls:
    def test_empty(self):
        assert extract_article_urls("") == []

    def test_no_links(self):
        md = "## 제목\n\n본문에 링크 없음. 그냥 텍스트.\n"
        assert extract_article_urls(md) == []

    def test_single_link(self):
        md = "기사 [OpenAI 발표](https://openai.com/blog) 참고."
        rows = extract_article_urls(md)
        assert rows == [{"title": "OpenAI 발표", "url": "https://openai.com/blog"}]

    def test_multiple_links(self):
        md = (
            "* [Reuters 기사](https://reuters.com/a)\n"
            "* [Bloomberg 보도](https://bloomberg.com/b)\n"
            "* [Guardian](https://theguardian.com/c)\n"
        )
        rows = extract_article_urls(md)
        assert len(rows) == 3
        assert rows[0]["url"] == "https://reuters.com/a"
        assert rows[2]["title"] == "Guardian"

    def test_duplicate_urls_removed(self):
        md = "[A](https://x.com/p) [B](https://x.com/p) [C](https://y.com/q)"
        rows = extract_article_urls(md)
        assert len(rows) == 2
        assert {r["url"] for r in rows} == {"https://x.com/p", "https://y.com/q"}

    def test_caps_at_50(self):
        # 60개 생성
        md = "\n".join(
            f"* [기사{i}](https://example.com/{i})" for i in range(60)
        )
        rows = extract_article_urls(md)
        assert len(rows) == 50

    def test_skips_non_http(self):
        md = "[로컬](file:///etc/passwd) [정상](https://example.com)"
        rows = extract_article_urls(md)
        assert len(rows) == 1
        assert rows[0]["url"] == "https://example.com"


# ── IndustryScanService.__init__ ──


class TestInit:
    def test_default_max_iter(self):
        s = IndustryScanService()
        assert s.max_iter == 35

    def test_custom_max_iter(self):
        s = IndustryScanService({"industry_scan": {"max_iter": 50}})
        assert s.max_iter == 50

    def test_skill_path_override(self, tmp_path):
        skill = tmp_path / "skill.md"
        s = IndustryScanService({"industry_scan": {"skill_path": str(skill)}})
        assert s._skill_override == skill


# ── IndustryScanService.generate ──


class TestGenerate:
    @pytest.fixture
    def env_with_key(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_API_KEY", "test-key")

    def test_missing_api_key(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLAUDE_API_KEY", raising=False)
        skill = tmp_path / "skill.md"
        skill.write_text("# skill", encoding="utf-8")
        s = IndustryScanService({"industry_scan": {"skill_path": str(skill)}})
        with pytest.raises(IndustryScanError, match="CLAUDE_API_KEY"):
            s.generate("2026-05-14")

    def test_skill_path_not_exist(self, env_with_key, tmp_path):
        s = IndustryScanService({
            "industry_scan": {"skill_path": str(tmp_path / "missing.md")}
        })
        with pytest.raises(IndustryScanError, match="SKILL.md 미존재"):
            s.generate("2026-05-14")

    def test_happy_path(self, env_with_key, tmp_path):
        skill = tmp_path / "skill.md"
        skill.write_text("# skill", encoding="utf-8")
        s = IndustryScanService({"industry_scan": {"skill_path": str(skill)}})

        with patch("scripts.run_industry_scan.run") as mock_run, \
             patch("scripts.run_industry_scan.postprocess_to_daily_format") as mock_pp:
            # asyncio.run()이 await할 coroutine 반환을 흉내
            async def fake_run(*a, **kw):
                return "raw report content"
            mock_run.side_effect = fake_run
            mock_pp.return_value = "## 일간 뉴스레터\n\n본문..."

            result = s.generate("2026-05-14")

        assert result == "## 일간 뉴스레터\n\n본문..."
        mock_pp.assert_called_once_with("raw report content", "test-key")

    def test_run_raises_wrapped(self, env_with_key, tmp_path):
        skill = tmp_path / "skill.md"
        skill.write_text("# skill", encoding="utf-8")
        s = IndustryScanService({"industry_scan": {"skill_path": str(skill)}})

        with patch("scripts.run_industry_scan.run") as mock_run:
            async def fake_run(*a, **kw):
                raise RuntimeError("max_iter 도달")
            mock_run.side_effect = fake_run
            with pytest.raises(IndustryScanError, match="4-Pass run\\(\\) 실패"):
                s.generate("2026-05-14")

    def test_empty_raw_report_raises(self, env_with_key, tmp_path):
        skill = tmp_path / "skill.md"
        skill.write_text("# skill", encoding="utf-8")
        s = IndustryScanService({"industry_scan": {"skill_path": str(skill)}})

        with patch("scripts.run_industry_scan.run") as mock_run:
            async def fake_run(*a, **kw):
                return "   "
            mock_run.side_effect = fake_run
            with pytest.raises(IndustryScanError, match="비어있음"):
                s.generate("2026-05-14")

    def test_postprocess_raises_wrapped(self, env_with_key, tmp_path):
        skill = tmp_path / "skill.md"
        skill.write_text("# skill", encoding="utf-8")
        s = IndustryScanService({"industry_scan": {"skill_path": str(skill)}})

        with patch("scripts.run_industry_scan.run") as mock_run, \
             patch("scripts.run_industry_scan.postprocess_to_daily_format") as mock_pp:
            async def fake_run(*a, **kw):
                return "raw"
            mock_run.side_effect = fake_run
            mock_pp.side_effect = ValueError("응답 비어있음")
            with pytest.raises(IndustryScanError, match="후처리"):
                s.generate("2026-05-14")
