"""tests/test_news_service.py — GNews API 뉴스 수집 서비스 TDD 테스트"""
import json
from unittest.mock import patch, MagicMock

import pytest

from src.news_service import GNewsService


SAMPLE_GNEWS_RESPONSE = {
    "totalArticles": 3,
    "articles": [
        {
            "title": "AI Revolution in Software",
            "description": "AI is transforming the software industry",
            "url": "https://example.com/article1",
            "publishedAt": "2026-03-29T10:00:00Z",
            "source": {"name": "TechNews", "url": "https://technews.com"},
        },
        {
            "title": "GPU Demand Surges",
            "description": "GPU market sees unprecedented growth",
            "url": "https://example.com/article2",
            "publishedAt": "2026-03-29T08:00:00Z",
            "source": {"name": "HardwareWeekly", "url": "https://hwweekly.com"},
        },
        {
            "title": "AI Policy Update",
            "description": "New AI regulations proposed",
            "url": "https://example.com/article3",
            "publishedAt": "2026-03-29T06:00:00Z",
            "source": {"name": "PolicyDaily", "url": "https://policydaily.com"},
        },
    ],
}

SAMPLE_CONFIG = {
    "gnews": {
        "queries": [
            "software industry AI",
            "AI regulation policy",
        ],
        "lang": "en",
        "max_per_query": 50,
    },
    "newsletter": {"max_articles": 25},
}


@pytest.fixture
def service():
    return GNewsService(SAMPLE_CONFIG, api_key="test_key")


class TestGNewsServiceInit:
    def test_queries_loaded(self, service):
        assert len(service.queries) == 2
        assert "software industry AI" in service.queries

    def test_max_articles(self, service):
        assert service.max_articles == 25


class TestQueryGNews:
    @patch("src.news_service.requests.get")
    def test_successful_query(self, mock_get, service):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_GNEWS_RESPONSE
        mock_get.return_value = mock_resp

        articles = service._query_gnews("software industry AI")
        assert len(articles) == 3
        assert articles[0]["title"] == "AI Revolution in Software"
        assert articles[0]["url"] == "https://example.com/article1"
        assert articles[0]["source_name"] == "TechNews"

    @patch("src.news_service.requests.get")
    def test_api_params(self, mock_get, service):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"articles": []}
        mock_get.return_value = mock_resp

        service._query_gnews("test query")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        params = call_kwargs[1]["params"] if "params" in call_kwargs[1] else call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("params")
        assert params["q"] == "test query"
        assert params["lang"] == "en"
        assert params["apikey"] == "test_key"

    @patch("src.news_service.requests.get")
    def test_api_failure_raises(self, mock_get, service):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.raise_for_status.side_effect = Exception("Rate limited")
        mock_get.return_value = mock_resp

        with pytest.raises(Exception):
            service._query_gnews("test")


class TestDedup:
    def test_dedup_by_url(self, service):
        articles = [
            {"url": "https://example.com/1", "title": "A", "published_at": "2026-03-29T10:00:00Z"},
            {"url": "https://example.com/1", "title": "A dup", "published_at": "2026-03-29T10:00:00Z"},
            {"url": "https://example.com/2", "title": "B", "published_at": "2026-03-29T09:00:00Z"},
        ]
        result = service._dedup_articles(articles)
        assert len(result) == 2
        urls = [a["url"] for a in result]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls


class TestSortAndLimit:
    def test_sort_descending(self, service):
        articles = [
            {"title": "Old", "published_at": "2026-03-29T06:00:00Z"},
            {"title": "New", "published_at": "2026-03-29T10:00:00Z"},
            {"title": "Mid", "published_at": "2026-03-29T08:00:00Z"},
        ]
        result = service._sort_and_limit(articles)
        assert result[0]["title"] == "New"
        assert result[-1]["title"] == "Old"

    def test_limit_to_max(self, service):
        articles = [
            {"title": f"Article {i}", "published_at": f"2026-03-29T{i:02d}:00:00Z"}
            for i in range(30)
        ]
        result = service._sort_and_limit(articles)
        assert len(result) == 25


class TestFetchArticles:
    @patch("src.news_service.requests.get")
    def test_full_fetch_pipeline(self, mock_get, service):
        """2개 쿼리 실행 → 중복제거 → 정렬 → 제한."""
        # 첫 쿼리: article1, article2
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {
            "articles": [
                {"title": "A1", "url": "https://example.com/1",
                 "description": "d1", "publishedAt": "2026-03-29T10:00:00Z",
                 "source": {"name": "S1", "url": ""}},
                {"title": "A2", "url": "https://example.com/2",
                 "description": "d2", "publishedAt": "2026-03-29T08:00:00Z",
                 "source": {"name": "S2", "url": ""}},
            ]
        }
        # 둘째 쿼리: article2(중복), article3
        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            "articles": [
                {"title": "A2 dup", "url": "https://example.com/2",
                 "description": "d2", "publishedAt": "2026-03-29T08:00:00Z",
                 "source": {"name": "S2", "url": ""}},
                {"title": "A3", "url": "https://example.com/3",
                 "description": "d3", "publishedAt": "2026-03-29T06:00:00Z",
                 "source": {"name": "S3", "url": ""}},
            ]
        }
        mock_get.side_effect = [resp1, resp2]

        articles = service.fetch_articles()

        assert len(articles) == 3
        # 최신순
        assert articles[0]["title"] == "A1"
        assert articles[-1]["title"] == "A3"
        # 중복 제거 확인
        urls = [a["url"] for a in articles]
        assert len(set(urls)) == 3
