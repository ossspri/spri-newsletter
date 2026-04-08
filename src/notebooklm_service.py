"""src/notebooklm_service.py — NotebookLM 연동 (원천 자료 저장)

PRD 4.2: 뉴스레터에 인용된 기사 URL을 NotebookLM 주간 노트북에 소스로 저장한다.
PRD 10: NotebookLM 저장 실패 시 에러 로그 기록, 파이프라인은 계속 진행 (비핵심 단계).

notebooklm-py (https://github.com/teng-lin/notebooklm-py) 사용.
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

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


_DEFAULT_STORAGE = Path(os.environ.get("USERPROFILE", "~")) / ".notebooklm" / "storage_state.json"


def check_nlm_auth(storage_path: Path = _DEFAULT_STORAGE) -> dict:
    """NotebookLM 인증 상태를 확인한다.

    storage_state.json의 쿠키 만료를 검사하고, 쿠키가 유효하면
    실제 API 호출(notebooks.list)로 인증을 검증한다.

    Returns:
        {"valid": bool, "reason": str, "login_date": str|None,
         "expires_in_hours": float|None}
    """
    # 1) storage_state.json 존재 여부
    if not storage_path.exists():
        return {"valid": False, "reason": "storage_state.json 없음 — notebooklm login 필요",
                "login_date": None, "expires_in_hours": None}

    # 2) 쿠키 만료 검사
    try:
        data = json.loads(storage_path.read_text(encoding="utf-8"))
    except Exception:
        return {"valid": False, "reason": "storage_state.json 파싱 실패",
                "login_date": None, "expires_in_hours": None}

    now = time.time()
    login_date = datetime.fromtimestamp(storage_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

    # 핵심 쿠키 중 가장 빨리 만료되는 것 확인
    key_cookie_names = {"SID", "HSID", "SSID", "OSID", "SIDCC",
                        "__Secure-1PSIDTS", "__Secure-1PSIDRTS"}
    earliest_exp = float("inf")
    for cookie in data.get("cookies", []):
        if cookie["name"] in key_cookie_names and "google" in cookie.get("domain", ""):
            exp = cookie.get("expires", 0)
            if 0 < exp < earliest_exp:
                earliest_exp = exp

    if earliest_exp < now:
        hours_ago = (now - earliest_exp) / 3600
        return {"valid": False,
                "reason": f"세션 쿠키 만료됨 ({hours_ago:.0f}시간 전) — notebooklm login 필요",
                "login_date": login_date, "expires_in_hours": 0}

    hours_left = (earliest_exp - now) / 3600

    # 3) 실제 API 호출로 검증
    try:
        asyncio.run(_check_api())
        return {"valid": True,
                "reason": f"인증 유효 (만료까지 {hours_left:.0f}시간)",
                "login_date": login_date, "expires_in_hours": round(hours_left, 1)}
    except Exception as e:
        err_msg = str(e)
        if "Authentication expired" in err_msg or "Redirected to" in err_msg:
            return {"valid": False,
                    "reason": "세션 만료 (API 확인) — notebooklm login 필요",
                    "login_date": login_date, "expires_in_hours": 0}
        return {"valid": False,
                "reason": f"API 호출 실패: {err_msg}",
                "login_date": login_date, "expires_in_hours": round(hours_left, 1)}


async def _check_api():
    """경량 API 호출로 인증 유효성을 확인한다."""
    async with await NotebookLMClient.from_storage() as client:
        await client.notebooks.list()


import queue
import threading

_reauth_thread = None
_reauth_cmd_q = None   # Flask → Playwright 스레드
_reauth_res_q = None   # Playwright 스레드 → Flask


def _reauth_worker(cmd_q: queue.Queue, res_q: queue.Queue):
    """Playwright 전용 스레드.  open/save/cleanup 명령을 처리한다."""
    from playwright.sync_api import sync_playwright
    from notebooklm.paths import get_storage_path, get_browser_profile_dir

    pw = None
    context = None
    page = None
    storage_path = None

    def cleanup():
        nonlocal pw, context, page
        try:
            if context:
                context.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass
        pw = context = page = None

    while True:
        cmd = cmd_q.get()
        if cmd == "open":
            cleanup()
            try:
                storage_path = get_storage_path()
                browser_profile = get_browser_profile_dir()
                storage_path.parent.mkdir(parents=True, exist_ok=True)
                browser_profile.mkdir(parents=True, exist_ok=True)

                pw = sync_playwright().start()
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(browser_profile),
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--password-store=basic",
                    ],
                    ignore_default_args=["--enable-automation"],
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto("https://notebooklm.google.com/")
                res_q.put({"success": True})
            except Exception as e:
                cleanup()
                res_q.put({"success": False, "error": str(e)})

        elif cmd == "save":
            if not context or not page:
                res_q.put({"success": False, "valid": False,
                           "reason": "열려 있는 재인증 브라우저 없음"})
                continue
            try:
                page.goto("https://accounts.google.com/", wait_until="load")
                page.goto("https://notebooklm.google.com/", wait_until="load")

                current_url = page.url
                if "notebooklm.google.com" not in current_url:
                    cleanup()
                    res_q.put({"success": False, "valid": False,
                               "reason": f"NotebookLM 로그인 미완료 (현재 URL: {current_url})"})
                    continue

                context.storage_state(path=str(storage_path))
                cleanup()
                res_q.put({"success": True, "_check_auth": True})
            except Exception as e:
                cleanup()
                res_q.put({"success": False, "valid": False, "reason": str(e)})

        elif cmd == "quit":
            cleanup()
            res_q.put({"done": True})
            break


def _ensure_worker():
    """Playwright 워커 스레드가 없으면 시작한다."""
    global _reauth_thread, _reauth_cmd_q, _reauth_res_q
    if _reauth_thread and _reauth_thread.is_alive():
        return
    _reauth_cmd_q = queue.Queue()
    _reauth_res_q = queue.Queue()
    _reauth_thread = threading.Thread(
        target=_reauth_worker, args=(_reauth_cmd_q, _reauth_res_q), daemon=True
    )
    _reauth_thread.start()


def reauth_nlm_open() -> dict:
    """Playwright 브라우저를 열어 Google 로그인 페이지를 표시한다.

    사용자가 브라우저에서 로그인을 완료한 뒤 reauth_nlm_save()를 호출해야 한다.

    Returns:
        {"success": bool, "error": str|None}
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        return {"success": False, "error": "Playwright 미설치. pip install notebooklm[browser] && playwright install chromium"}

    _ensure_worker()
    _reauth_cmd_q.put("open")
    result = _reauth_res_q.get(timeout=30)
    if result.get("success"):
        logger.info("NotebookLM 재인증 브라우저 열림")
    else:
        logger.error("NotebookLM 재인증 브라우저 열기 실패: %s", result.get("error"))
    return result


def reauth_nlm_save() -> dict:
    """열려 있는 브라우저에서 인증 쿠키를 저장하고 브라우저를 닫는다.

    Returns:
        {"success": bool, "valid": bool, "reason": str}
    """
    if not _reauth_thread or not _reauth_thread.is_alive():
        return {"success": False, "valid": False, "reason": "열려 있는 재인증 브라우저 없음"}

    _reauth_cmd_q.put("save")
    result = _reauth_res_q.get(timeout=30)

    if result.get("_check_auth"):
        auth = check_nlm_auth()
        logger.info("NotebookLM 재인증 완료: %s", auth["reason"])
        return {"success": True, **auth}

    logger.error("NotebookLM 재인증 저장 실패: %s", result.get("reason"))
    return result


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
