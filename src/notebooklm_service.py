"""src/notebooklm_service.py — NotebookLM 연동 (원천 자료 저장)

PRD 4.2: 뉴스레터에 인용된 기사 URL을 NotebookLM 주간 노트북에 소스로 저장한다.
PRD 10: NotebookLM 저장 실패 시 에러 로그 기록, 파이프라인은 계속 진행 (비핵심 단계).

notebooklm-py (https://github.com/teng-lin/notebooklm-py) 사용.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from notebooklm import NotebookLMClient

logger = logging.getLogger(__name__)


def _get_monday_label(date_str: str, prefix: str = "SPRi") -> str:
    """해당 날짜가 속한 주의 월요일 기준 노트북 레이블을 생성한다.

    PRD 4.2.2: SPRi_{연도}_{해당 주의 월요일 날짜 MMDD}
    예: 2026-03-29(일) → 해당 주 월요일 = 2026-03-23 → SPRi_2026_0323

    Args:
        date_str: 날짜 문자열 (YYYY-MM-DD)
        prefix: 노트북 접두사 (기본 'SPRi')

    Returns:
        노트북 레이블 문자열
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    monday = dt - timedelta(days=dt.weekday())
    return f"{prefix}_{monday.year}_{monday.strftime('%m%d')}"


class NotebookLMService:
    """notebooklm-py를 사용한 NotebookLM 연동 서비스."""

    def __init__(self, config: dict):
        """서비스를 초기화한다.

        Args:
            config: config.yaml 설정 dict (notebooklm.notebook_prefix 포함)
        """
        nlm_config = config.get("notebooklm", {})
        self.prefix = nlm_config.get("notebook_prefix", "SPRi")

    def save_sources(
        self,
        date_str: str,
        articles: list[dict],
        newsletter_markdown: str = None,
    ) -> str:
        """기사 URL과 뉴스레터 본문을 NotebookLM 주간 노트북에 저장한다.

        동기 래퍼: 내부적으로 asyncio 이벤트 루프를 실행한다.

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD)
            articles: 기사 dict 목록 (title, url 필수)
            newsletter_markdown: (선택) 뉴스레터 마크다운 본문

        Returns:
            사용된 노트북 ID

        Raises:
            Exception: NotebookLM API 오류 시
        """
        return asyncio.run(
            self._save_sources_async(date_str, articles, newsletter_markdown)
        )

    async def _save_sources_async(
        self,
        date_str: str,
        articles: list[dict],
        newsletter_markdown: str = None,
    ) -> str:
        """기사 URL과 뉴스레터 본문을 비동기로 저장한다."""
        notebook_title = _get_monday_label(date_str, self.prefix)
        logger.info("NotebookLM 노트북: %s", notebook_title)

        async with await NotebookLMClient.from_storage() as client:
            # 기존 노트북 검색 또는 신규 생성
            notebook_id = await self._get_or_create_notebook(
                client, notebook_title
            )

            # 기존 소스 URL/제목 조회 (중복 방지)
            existing_sources = await client.sources.list(notebook_id)
            existing_urls = {s.url for s in existing_sources if s.url}
            existing_titles = {s.title for s in existing_sources if s.title}

            # 기사 URL 소스 추가
            for article in articles:
                if article["url"] in existing_urls:
                    logger.info("소스 중복 건너뜀: %s", article["url"])
                    continue
                try:
                    await client.sources.add_url(
                        notebook_id, article["url"]
                    )
                    logger.info(
                        "소스 추가: %s -> %s", article["title"], notebook_title
                    )
                except Exception as e:
                    logger.warning(
                        "소스 추가 실패 (계속 진행): %s - %s",
                        article["url"], e,
                    )

            # (선택) 뉴스레터 본문을 텍스트 소스로 추가
            if newsletter_markdown:
                source_title = f"Daily_브리핑_{date_str}"
                if source_title in existing_titles:
                    logger.info("본문 소스 중복 건너뜀: %s", source_title)
                else:
                    try:
                        await client.sources.add_text(
                            notebook_id, source_title, newsletter_markdown
                        )
                        logger.info("뉴스레터 본문 소스 추가: %s", source_title)
                    except Exception as e:
                        logger.warning("본문 소스 추가 실패: %s", e)

        logger.info("NotebookLM 저장 완료: notebook_id=%s", notebook_id)
        return notebook_id

    async def _get_or_create_notebook(
        self, client: NotebookLMClient, title: str
    ) -> str:
        """제목으로 노트북을 찾거나 새로 생성한다.

        Args:
            client: NotebookLMClient 인스턴스
            title: 노트북 제목

        Returns:
            노트북 ID
        """
        notebooks = await client.notebooks.list()
        for nb in notebooks:
            if nb.title == title:
                logger.info("기존 노트북 발견: id=%s", nb.id)
                return nb.id

        nb = await client.notebooks.create(title)
        logger.info("새 노트북 생성: id=%s, title=%s", nb.id, title)
        return nb.id

    def delete_today_sources(self, date_str: str) -> dict:
        """오늘 날짜의 노트북에서 소스를 모두 삭제한다.

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD)

        Returns:
            삭제 결과 dict (notebook_title, deleted_count)
        """
        return asyncio.run(self._delete_today_sources_async(date_str))

    async def _delete_today_sources_async(self, date_str: str) -> dict:
        """오늘 날짜 노트북의 소스를 비동기로 삭제한다."""
        notebook_title = _get_monday_label(date_str, self.prefix)
        logger.info("NotebookLM 소스 삭제 대상 노트북: %s", notebook_title)

        async with await NotebookLMClient.from_storage() as client:
            notebooks = await client.notebooks.list()
            target = None
            for nb in notebooks:
                if nb.title == notebook_title:
                    target = nb
                    break

            if not target:
                logger.info("노트북 없음, 삭제 건너뜀: %s", notebook_title)
                return {"notebook_title": notebook_title, "deleted_count": 0}

            sources = await client.sources.list(target.id)
            deleted = 0
            for source in sources:
                try:
                    await client.sources.delete(target.id, source.id)
                    deleted += 1
                    logger.info("소스 삭제: %s", source.title or source.url)
                except Exception as e:
                    logger.warning("소스 삭제 실패 (계속 진행): %s - %s",
                                   source.id, e)

        logger.info("NotebookLM 소스 삭제 완료: %s, %d건", notebook_title, deleted)
        return {"notebook_title": notebook_title, "deleted_count": deleted}

    def get_notebook_label(self, date_str: str) -> str:
        """날짜에 해당하는 노트북 레이블을 반환한다.

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD)

        Returns:
            노트북 레이블 문자열
        """
        return _get_monday_label(date_str, self.prefix)
