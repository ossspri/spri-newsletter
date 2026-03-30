"""src/news_service.py — GNews API 연동 (뉴스 수집)"""
import logging

import requests

from src.utils import retry, get_kst_24h_ago_utc

logger = logging.getLogger(__name__)

GNEWS_API_URL = "https://gnews.io/api/v4/search"


class GNewsService:
    def __init__(self, config: dict, api_key: str):
        gnews_cfg = config.get("gnews", {})
        self.queries = gnews_cfg.get("queries", [])
        self.lang = gnews_cfg.get("lang", "en")
        self.max_per_query = gnews_cfg.get("max_per_query", 50)
        self.max_articles = config.get("newsletter", {}).get("max_articles", 25)
        self.api_key = api_key

    def fetch_articles(self) -> list[dict]:
        all_articles = []
        for query in self.queries:
            try:
                articles = self._query_gnews(query)
                all_articles.extend(articles)
                logger.info("쿼리 '%s': %d건 수집", query, len(articles))
            except Exception as e:
                logger.error("쿼리 '%s' 실패: %s", query, e)
                raise

        deduped = self._dedup_articles(all_articles)
        result = self._sort_and_limit(deduped)
        logger.info("최종 기사: %d건 (중복제거 후 %d -> 제한 %d)",
                     len(result), len(deduped), self.max_articles)
        return result

    @retry(max_retries=2, delay=10)
    def _query_gnews(self, keyword: str) -> list[dict]:
        from_time = get_kst_24h_ago_utc()
        params = {
            "q": keyword,
            "lang": self.lang,
            "from": from_time,
            "max": self.max_per_query,
            "apikey": self.api_key,
        }

        resp = requests.get(GNEWS_API_URL, params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()
        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title": a["title"],
                "url": a["url"],
                "description": a.get("description", ""),
                "source_name": a.get("source", {}).get("name", ""),
                "published_at": a["publishedAt"],
            })
        return articles

    def _dedup_articles(self, articles: list[dict]) -> list[dict]:
        seen_urls = set()
        unique = []
        for a in articles:
            if a["url"] not in seen_urls:
                seen_urls.add(a["url"])
                unique.append(a)
        return unique

    def _sort_and_limit(self, articles: list[dict], max_count: int = None) -> list[dict]:
        max_count = max_count or self.max_articles
        sorted_articles = sorted(articles, key=lambda a: a["published_at"], reverse=True)
        return sorted_articles[:max_count]
