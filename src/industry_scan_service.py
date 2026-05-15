"""src/industry_scan_service.py — A'(industry-scan) 본문 생성 운영 서비스.

`main.py run_daily_pipeline`에서 `features.news_mode == "industry_scan"`일 때
호출되어 일간 뉴스레터 마크다운을 생성한다.

내부적으로 `scripts/run_industry_scan.py`의 비동기 `run()` + `postprocess_to_daily_format()`을 그대로
재사용한다. 즉:
  1. prism repo의 `skills/industry-scan.md` 동적 로드
  2. prism-data MCP stdio 서브프로세스 기동
  3. Claude tool_use 루프(4-Pass) — 5~8분, 30+회 API 호출
  4. 후처리로 일간 6섹션 마크다운(~10K자) 변환

Config:
  features.news_mode: "industry_scan" | "gnews"
  features.news_mode_fallback_on_failure: bool — A' 실패 시 GNews 백업
  industry_scan.max_iter: int (default 35)
  industry_scan.skill_path: str | null — null이면 prism 기본 경로
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# scripts.run_industry_scan을 import할 수 있도록 PROJECT_ROOT를 sys.path에 추가.
# (scripts/는 패키지 __init__.py가 없는 namespace package로 동작)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class IndustryScanError(Exception):
    """A' 본문 생성 실패. main.py에서 잡아 fallback 결정."""


class IndustryScanService:
    """A'(industry-scan) 본문 생성 운영 서비스."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        is_cfg = self.config.get("industry_scan", {}) if self.config else {}
        self.max_iter: int = int(is_cfg.get("max_iter", 35))
        skill_override = is_cfg.get("skill_path")
        self._skill_override = Path(skill_override) if skill_override else None

    def generate(self, date_str: str) -> str:
        """A' 일간 뉴스레터 마크다운을 생성한다.

        Args:
            date_str: KST 날짜(YYYY-MM-DD). 현재는 로깅용으로만 사용. A'의
                날짜 인식은 `run()` 내부에서 `datetime.now()`로 처리됨.
        Returns:
            일간 뉴스레터 6섹션 포맷 마크다운 본문.
        Raises:
            IndustryScanError: 4-Pass 루프 미완성·후처리 실패·API 키 누락 등.
        """
        # lazy import — module top에서 import하면 mcp 미설치 환경에서 실패.
        try:
            from scripts.run_industry_scan import (
                run as _run_industry_scan,
                postprocess_to_daily_format,
                DEFAULT_SKILL_PATH,
            )
        except ImportError as e:
            raise IndustryScanError(
                f"industry-scan 모듈 import 실패 (mcp/anthropic 미설치 가능): {e}"
            ) from e

        skill_path = self._skill_override or DEFAULT_SKILL_PATH
        if not Path(skill_path).exists():
            raise IndustryScanError(
                f"prism SKILL.md 미존재: {skill_path}. prism repo가 본인 PC에 "
                f"설치되어 있는지 확인하세요."
            )

        api_key = os.getenv("CLAUDE_API_KEY", "")
        if not api_key:
            raise IndustryScanError("CLAUDE_API_KEY 미설정")

        logger.info("A'(industry-scan) 본문 생성 시작 (date=%s, max_iter=%d)",
                    date_str, self.max_iter)
        try:
            raw_report = asyncio.run(
                _run_industry_scan(Path(skill_path), max_iter=self.max_iter)
            )
        except Exception as e:
            raise IndustryScanError(f"4-Pass run() 실패: {e}") from e

        if not raw_report or not raw_report.strip():
            raise IndustryScanError("4-Pass 결과 비어있음")

        logger.info("A' raw 보고서 %d자, 후처리 단계 진입", len(raw_report))
        try:
            final = postprocess_to_daily_format(raw_report, api_key)
        except Exception as e:
            raise IndustryScanError(f"후처리(postprocess) 실패: {e}") from e

        if not final or not final.strip():
            raise IndustryScanError("후처리 응답 비어있음")

        logger.info("A' 본문 완성 (%d자)", len(final))
        return final


def extract_article_urls(markdown: str) -> list[dict]:
    """A' 본문 마크다운에서 인용 기사 URL을 추출해 archive 저장 형식으로 변환.

    A는 GNews 25건의 명시 리스트가 있지만 A'은 본문 내 인라인 인용만 있음.
    `archive_articles`에 저장할 수 있도록 (title, url) dict 리스트로 변환.

    Args:
        markdown: A'의 일간 뉴스레터 본문.
    Returns:
        [{"title": str, "url": str}, ...] — 중복 url 제거됨. 최대 50건.
    """
    import re

    seen: set[str] = set()
    rows: list[dict] = []
    # 마크다운 링크 패턴: [title](url)
    for m in re.finditer(r"\[([^\[\]\n]+)\]\((https?://[^)\s]+)\)", markdown):
        title, url = m.group(1).strip(), m.group(2).strip()
        if url in seen:
            continue
        seen.add(url)
        rows.append({"title": title[:200], "url": url})
        if len(rows) >= 50:
            break
    return rows
