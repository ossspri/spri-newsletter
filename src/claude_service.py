"""src/claude_service.py — Anthropic Claude API 연동 (보고서 생성)

PRD 3.2: Claude API를 호출하여 SPRi 양식의 마크다운 뉴스레터를 생성한다.
PRD 10: Claude API 실패 시 3회 재시도 (30초 대기).
reference/runDailyAutomation.js의 후처리 로직 보존.
"""
import logging
import re

import anthropic

from src.prompts import (
    build_daily_prompt,
    build_weekly_prompt,
    format_articles_for_prompt,
)
from src.utils import retry

logger = logging.getLogger(__name__)


class ClaudeService:
    def __init__(self, config: dict, api_key: str):
        newsletter_cfg = config.get("newsletter", {})
        self.model = newsletter_cfg.get("model", "claude-sonnet-4-20250514")
        self.max_tokens = newsletter_cfg.get("max_tokens", 4096)
        self.client = anthropic.Anthropic(api_key=api_key)

    def generate_daily(self, articles: list[dict], existing_summaries: str = "") -> str:
        """Daily 뉴스레터 마크다운을 생성한다.

        Args:
            articles: 수집된 기사 목록 (dict with title, url, description, ...)
            existing_summaries: 이전 뉴스레터 기사 제목들 (중복 배제용)

        Returns:
            마크다운 형식의 뉴스레터 본문
        """
        article_text = format_articles_for_prompt(articles)
        prompt = build_daily_prompt(article_text, existing_summaries)

        logger.info("Daily 뉴스레터 생성 시작 (기사 %d건, 모델: %s)", len(articles), self.model)
        raw = self._call_api(prompt)
        result = self._postprocess(raw)
        logger.info("Daily 뉴스레터 생성 완료 (%d자)", len(result))
        return result

    def generate_weekly(self, articles: list[dict], existing_summaries: str = "") -> str:
        """Weekly 보고서 마크다운을 생성한다."""
        article_text = format_articles_for_prompt(articles)
        prompt = build_weekly_prompt(article_text, existing_summaries)

        logger.info("Weekly 보고서 생성 시작 (기사 %d건, 모델: %s)", len(articles), self.model)
        raw = self._call_api(prompt)
        result = self._postprocess(raw)
        logger.info("Weekly 보고서 생성 완료 (%d자)", len(result))
        return result

    @retry(max_retries=3, delay=30)
    def _call_api(self, prompt: str) -> str:
        """Claude Messages API를 호출한다 (PRD 부록 B 사양)."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text
        if not text or not text.strip():
            raise ValueError("Claude API가 빈 응답을 반환했습니다.")
        return text

    def _postprocess(self, raw_text: str) -> str:
        """리포트 시작 이전의 전처리 텍스트를 제거한다.

        reference/runDailyAutomation.js:140-155 후처리 로직 보존.
        """
        # 리포트 본문 시작 패턴
        patterns = [
            r"소프트웨어정책연구소",
            r"SPRi",
            r"글로벌 SW 산업 동향",
            r"## 1\.\s*개요",
        ]

        for pattern in patterns:
            match = re.search(pattern, raw_text)
            if match and match.start() > 0:
                raw_text = raw_text[match.start():]
                break

        return raw_text.strip()
