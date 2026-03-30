"""tests/test_claude_service.py — Claude API 연동 서비스 TDD 테스트"""
from unittest.mock import patch, MagicMock

import pytest

from src.claude_service import ClaudeService


SAMPLE_CONFIG = {
    "newsletter": {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
    },
}

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

SAMPLE_REPORT = """\
## 1. 개요

**AI가 SW 산업 전반을 재편하고 있음**
글로벌 AI 기술이 소프트웨어 산업의 개발, 유통, 운영 전 과정에 걸쳐 혁신적 변화를 주도하고 있음.
주요 빅테크 기업들이 AI 기반 전략을 가속화하고 있으며, 반도체 수요도 급증하는 추세임.
정책적으로도 AI 규제 프레임워크 논의가 활발하게 진행되고 있음.

## 2. 정책/법제

**EU AI Act 시행 준비 본격화**
유럽연합이 AI법 세부 시행 규칙을 확정하고 기업들의 준수 기한을 발표함.
* [AI Revolution in Software](https://example.com/article1)

## 3. 기업/산업

**빅테크 GPU 확보 경쟁 심화**
주요 클라우드 기업들의 GPU 인프라 투자가 전년 대비 200% 이상 증가함.
* [GPU Demand Surges](https://example.com/article2)

## 4. 인력/교육

※ 해당 기간 주요 신규 동향 없음

## 5. 기술/연구

※ 해당 기간 주요 신규 동향 없음

## 6. 하드웨어/인프라

※ 해당 기간 주요 신규 동향 없음"""


@pytest.fixture
def service():
    with patch("src.claude_service.anthropic.Anthropic") as mock_cls:
        svc = ClaudeService(SAMPLE_CONFIG, api_key="test-key")
        yield svc


class TestClaudeServiceInit:
    def test_model_from_config(self, service):
        assert service.model == "claude-sonnet-4-20250514"

    def test_max_tokens_from_config(self, service):
        assert service.max_tokens == 4096

    def test_default_values(self):
        with patch("src.claude_service.anthropic.Anthropic"):
            svc = ClaudeService({}, api_key="test")
            assert svc.model == "claude-sonnet-4-20250514"
            assert svc.max_tokens == 4096


class TestPostprocess:
    def test_strips_preamble_before_section(self, service):
        raw = "물론입니다. 리포트를 작성하겠습니다.\n\n## 1. 개요\n본문 내용"
        result = service._postprocess(raw)
        assert result.startswith("## 1. 개요")

    def test_strips_preamble_before_spri(self, service):
        raw = "네, 아래와 같이 작성합니다.\n\n소프트웨어정책연구소 리포트\n## 1. 개요"
        result = service._postprocess(raw)
        assert result.startswith("소프트웨어정책연구소")

    def test_no_preamble_unchanged(self, service):
        raw = "## 1. 개요\n본문 내용"
        result = service._postprocess(raw)
        assert result == raw

    def test_whitespace_stripped(self, service):
        raw = "  \n## 1. 개요\n본문  \n  "
        result = service._postprocess(raw)
        assert result == "## 1. 개요\n본문"

    def test_spri_keyword_detected(self, service):
        raw = "여기 리포트입니다: SPRi 글로벌 동향\n## 1. 개요"
        result = service._postprocess(raw)
        assert result.startswith("SPRi")


class TestCallAPI:
    def test_successful_call(self, service):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=SAMPLE_REPORT)]
        service.client.messages.create.return_value = mock_response

        result = service._call_api("test prompt")
        assert "## 1. 개요" in result

        service.client.messages.create.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": "test prompt"}],
        )

    def test_empty_response_raises(self, service):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="")]
        service.client.messages.create.return_value = mock_response

        with pytest.raises(ValueError, match="빈 응답"):
            service._call_api("test prompt")

    def test_api_error_raises(self, service):
        service.client.messages.create.side_effect = Exception("API error")
        with pytest.raises(Exception):
            service._call_api("test prompt")


class TestGenerateDaily:
    def test_generate_daily_returns_report(self, service):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=SAMPLE_REPORT)]
        service.client.messages.create.return_value = mock_response

        result = service.generate_daily(SAMPLE_ARTICLES, "existing summary")
        assert "## 1. 개요" in result
        assert "AI" in result

    def test_generate_daily_with_no_summaries(self, service):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=SAMPLE_REPORT)]
        service.client.messages.create.return_value = mock_response

        result = service.generate_daily(SAMPLE_ARTICLES)
        assert "## 1. 개요" in result


class TestGenerateWeekly:
    def test_generate_weekly_returns_report(self, service):
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=SAMPLE_REPORT)]
        service.client.messages.create.return_value = mock_response

        result = service.generate_weekly(SAMPLE_ARTICLES, "existing")
        assert "## 1. 개요" in result
