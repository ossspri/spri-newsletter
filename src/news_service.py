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
        self.max_per_query = gnews_cfg.get("max_per_query", 25)
        self.search_in = gnews_cfg.get("search_in", "")
        self.source_whitelist = [s.lower() for s in gnews_cfg.get("source_whitelist", [])]
        self.fallback_queries = gnews_cfg.get("fallback_queries", [])
        self.min_articles = gnews_cfg.get("min_articles", 0)
        self.max_articles = config.get("newsletter", {}).get("max_articles", 25)
        self.api_key = api_key

    def fetch_articles(self) -> list[dict]:
        all_articles = []
        total_raw = 0
        for query in self.queries:
            try:
                raw = self._query_gnews(query)
                total_raw += len(raw)
                filtered = self._filter_by_source(raw)
                all_articles.extend(filtered)
                logger.info("쿼리 '%s': %d건 수집 → %d건 통과(화이트리스트)",
                            query, len(raw), len(filtered))
            except Exception as e:
                logger.error("쿼리 '%s' 실패: %s", query, e)
                raise

        deduped = self._dedup_articles(all_articles)

        # Fallback 가드: 통과 기사가 임계값 미만이면 fallback_queries로 보충 수집.
        # fallback 결과에도 화이트리스트를 적용해 노이즈 회귀를 방지한다.
        if len(deduped) < self.min_articles and self.fallback_queries:
            logger.warning("화이트리스트 통과 %d건 < 최소 %d건 — fallback 쿼리 실행 (%d개)",
                           len(deduped), self.min_articles, len(self.fallback_queries))
            fb_raw_total = 0
            fb_filtered = []
            for query in self.fallback_queries:
                try:
                    raw = self._query_gnews(query)
                    fb_raw_total += len(raw)
                    passed = self._filter_by_source(raw)
                    fb_filtered.extend(passed)
                    logger.info("fallback 쿼리 '%s': %d건 수집 → %d건 통과", query, len(raw), len(passed))
                except Exception as e:
                    logger.error("fallback 쿼리 '%s' 실패: %s", query, e)
                    # fallback 실패는 치명적이지 않으므로 계속 진행
                    continue
            deduped = self._dedup_articles(deduped + fb_filtered)
            logger.info("fallback 후 총 %d건 (fallback 원본 %d → 통과 %d, 누적 중복제거 후 %d)",
                        len(deduped), fb_raw_total, len(fb_filtered), len(deduped))

        result = self._sort_and_limit(deduped)
        logger.info("최종 기사: %d건 (원본 %d → 화이트리스트 통과 %d → 중복제거 %d → 제한 %d)",
                     len(result), total_raw, len(all_articles), len(deduped), self.max_articles)
        return result

    def _filter_by_source(self, articles: list[dict]) -> list[dict]:
        if not self.source_whitelist:
            return articles
        return [a for a in articles
                if any(w in a.get("source_name", "").lower() for w in self.source_whitelist)]

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
        if self.search_in:
            params["in"] = self.search_in

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
