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

    def generate_weekly(
        self,
        articles: list[dict],
        existing_summaries: str = "",
        reports: list[dict] | None = None,
        expert_insight: str = "",
    ) -> str:
        """Weekly 보고서 마크다운을 생성한다.

        Args:
            articles: 선별된 기사 list.
            existing_summaries: 과거 발송 기사 제목 (중복 배제).
            reports: 수동 첨부 1차 자료 (PR3). None/빈 list면 기존 동작.
                안전 한도: 상위 5건까지만 prompt에 주입 (체크박스로 더
                선택해도 토큰 폭증 방지).
            expert_insight: 전문가가 직접 입력한 금주 핵심 인사이트.
                LLM이 이를 반영하여 관련 기사·보고서 요약을 증강.
        """
        article_text = format_articles_for_prompt(articles)
        trimmed_reports = (reports or [])[:5]
        prompt = build_weekly_prompt(
            article_text, existing_summaries,
            reports=trimmed_reports or None,
            expert_insight=expert_insight or "",
        )

        logger.info(
            "Weekly 보고서 생성 시작 (기사 %d건, 보고서 %d건, 인사이트 %d자, 모델: %s)",
            len(articles), len(trimmed_reports), len(expert_insight or ""), self.model,
        )
        raw = self._call_api(prompt)
        result = self._postprocess(raw)
        logger.info("Weekly 보고서 생성 완료 (%d자)", len(result))
        return result

    def summarize_report_text(
        self,
        full_text: str,
        max_chars: int = 1500,
    ) -> str:
        """수동 첨부 보고서의 전문을 1차 요약한다 (Weekly prompt 주입용).

        용도: PR2 — Weekly '수동 보고서 추가' 흐름에서 사용자가 첨부한 PDF/HTML
        보고서의 전문(수만자)을 그대로 Weekly 생성 프롬프트에 넣으면 토큰
        폭발이 일어남. 본 메서드로 1000~1500자 정도의 한국어 요약을 만들어
        prompt에 ``<reports>`` 블록 안에 주입한다.

        Args:
            full_text: pdfplumber/HTML 본문에서 추출한 전문.
            max_chars: 결과 요약의 대략 목표 길이 (모델에 가이드만 줌).

        Returns:
            한국어 요약 문자열. 실패 시 빈 문자열 (호출자가 fallback 처리).
            전문이 너무 짧으면 그대로 또는 살짝 정리한 형태로 반환.
        """
        if not full_text or not full_text.strip():
            return ""

        # 본문이 충분히 짧으면 요약 불필요
        if len(full_text) <= max_chars:
            return full_text.strip()

        prompt = (
            "다음은 1차 자료(연구보고서/백서/회사 발표)의 전문입니다. "
            "SPRi 주간 SW 산업 동향 보고서에 인용할 수 있도록 한국어로 "
            f"약 {max_chars}자 이내로 요약해주세요.\n\n"
            "요약 작성 지침:\n"
            "1. 핵심 수치·인용·구체적 사실을 우선 포함 (예: '76% of enterprises...').\n"
            "2. 보고서 발행 주체와 발표 시점을 명시.\n"
            "3. SW 산업·정책·기업 동향과 연관 있는 부분 우선.\n"
            "4. 일반론은 생략, 통계와 사례 위주.\n"
            "5. 요약 본문만 출력하고 부가 설명은 금지.\n\n"
            "<report_text>\n"
            f"{full_text}\n"
            "</report_text>"
        )

        try:
            raw = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ).content[0].text
            summary = (raw or "").strip()
            logger.info("보고서 요약 완료 (%d자 → %d자)", len(full_text), len(summary))
            return summary
        except Exception as e:
            logger.warning("보고서 요약 실패, 빈 문자열 반환: %s", e)
            return ""

    def translate_articles(self, articles: list[dict]) -> list[dict]:
        """기사 제목과 설명을 한국어로 번역한다."""
        if not articles:
            return articles

        lines = []
        for i, a in enumerate(articles):
            lines.append(f"[{i}] TITLE: {a['title']}")
            lines.append(f"[{i}] DESC: {a.get('description', '')}")

        prompt = (
            "아래 뉴스 기사의 제목(TITLE)과 설명(DESC)을 한국어로 번역해주세요.\n"
            "반드시 동일한 형식([번호] TITLE: ... / [번호] DESC: ...)으로 출력하세요.\n"
            "이미 한국어인 항목은 그대로 유지하세요.\n"
            "번역만 출력하고 다른 설명은 하지 마세요.\n\n"
            + "\n".join(lines)
        )

        try:
            raw = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ).content[0].text

            translated = list(articles)  # shallow copy
            for line in raw.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                m = re.match(r"\[(\d+)\]\s*(TITLE|DESC):\s*(.*)", line)
                if m:
                    idx, field, value = int(m.group(1)), m.group(2), m.group(3).strip()
                    if 0 <= idx < len(translated):
                        if translated[idx] is articles[idx]:
                            translated[idx] = dict(articles[idx])
                        if field == "TITLE":
                            translated[idx]["title"] = value
                        else:
                            translated[idx]["description"] = value
            return translated
        except Exception as e:
            logger.warning("기사 번역 실패, 원문 반환: %s", e)
            return articles

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
