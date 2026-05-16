"""main.py — SPRi 뉴스레터 자동화 시스템 CLI 진입점

PRD 7.2 Daily 파이프라인 11단계를 구현한다.
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

from src.db import (
    init_db,
    insert_daily_articles,
    get_existing_summaries,
    log_newsletter,
    archive_articles,
    check_today_sent,
)
from src.news_service import GNewsService
from src.claude_service import ClaudeService
from src.email_template import render_email_html, build_email_subject
from src.gmail_service import GmailService
from src.industry_scan_service import (
    IndustryScanService, IndustryScanError, extract_article_urls,
)
from src.google_auth import get_google_credentials
from src.utils import get_kst_date_str, get_kst_display_date

BASE_DIR = Path(__file__).resolve().parent


def load_config() -> dict:
    """config.yaml 또는 SPRI_CONFIG 환경변수로 지정된 변종 설정 파일을 로드한다.

    우선순위:
      1. 환경변수 ``SPRI_CONFIG`` 가 설정되어 있으면 그 경로(절대 또는 BASE_DIR 상대)
      2. 기본값 ``config.yaml`` (BASE_DIR 기준)

    동료 PC 배포 zip 은 ``config.windows-portable.yaml`` 을 동봉하고
    실행 스크립트(setup_local.bat 등)에서 ``set SPRI_CONFIG=config.windows-portable.yaml``
    로 지정하여 메인 운영자의 ``config.yaml`` 과 충돌 없이 다른 기본값을 사용한다.
    """
    override = os.environ.get("SPRI_CONFIG", "").strip()
    if override:
        config_path = Path(override)
        if not config_path.is_absolute():
            config_path = BASE_DIR / config_path
    else:
        config_path = BASE_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    log_file = BASE_DIR / log_cfg.get("file", "logs/spri.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    stdout_utf8 = open(sys.stdout.fileno(), mode="w", encoding="utf-8",
                       closefd=False, buffering=1)
    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(stdout_utf8),
        ],
    )


def run_daily_pipeline(config: dict, db_conn, cron: bool = False) -> None:
    """Daily 파이프라인 — PRD 7.2 11단계 실행.

    1. config.yaml, .env 로드 (완료 — main()에서 처리)
    2. GNews API 호출 → 기사 수집
    3. 중복 제거 + 25건 제한 → Google Sheets 저장
    4. 이전 뉴스레터 요약 조회 (중복 배제용)
    5. Claude API 호출 → 뉴스레터 마크다운 생성
    6. 마크다운 → HTML 변환
    7. Gmail API → Daily 수신자에게 발송
    8. (제거됨, 2026-05-15) 이전: Google Drive API → 구글 문서 생성
    9. (제거됨, 2026-05-15) 이전: notebooklm-py → 기사 URL 저장
    10. Google Sheets → 발송 이력 기록
    11. 로컬 백업 → .md 파일 저장

    Args:
        cron: True이면 멱등성 가드 활성 (cron 트리거 전용). False이면 항상 실행.
    """
    logger = logging.getLogger(__name__)
    logger.info("Daily 파이프라인 시작 (cron=%s)", cron)

    # cron 가드가 Gmail Sent를 진실의 원천으로 사용하도록 먼저 주입.
    _try_attach_gmail(config, db_conn)

    if cron and check_today_sent(db_conn, "daily"):
        logger.info("오늘 Daily 이미 발송됨 - 파이프라인 스킵 (cron 멱등성 가드)")
        return

    date_str = get_kst_date_str()
    date_display = get_kst_display_date()
    recipients = config.get("recipients", {}).get("daily", [])

    # 2026-05-14 Phase 1: A → A' 통째 교체. news_mode flag로 분기.
    news_mode = config.get("features", {}).get("news_mode", "industry_scan")
    fallback_enabled = config.get("features", {}).get(
        "news_mode_fallback_on_failure", True
    )

    articles: list[dict] = []
    markdown_body: str = ""

    if news_mode == "industry_scan":
        # ── A' (industry-scan) 본문 생성 ──
        try:
            scan = IndustryScanService(config)
            markdown_body = scan.generate(date_str)
            logger.info("A'(industry-scan) 본문 생성 성공 (%d자)",
                        len(markdown_body))

            # A' 기사 → daily_articles 저장 (Weekly/Focus 탭 노출용)
            scan_articles = extract_article_urls(markdown_body)
            today_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            for sa in scan_articles:
                sa["published_at"] = today_iso
                sa["source_name"] = urlparse(sa["url"]).netloc.removeprefix("www.")
                sa["description"] = ""
            if scan_articles:
                inserted = insert_daily_articles(db_conn, scan_articles)
                logger.info("A' 기사 %d건 daily_articles 삽입", inserted)

        except IndustryScanError as e:
            if fallback_enabled:
                logger.warning(
                    "A' 실패 — GNews(A) fallback으로 전환: %s", e
                )
                news_mode = "gnews"
            else:
                logger.error(
                    "A' 실패 + fallback 비활성 — 오늘 발송 스킵: %s", e
                )
                log_newsletter(db_conn, "daily", 0, len(recipients), "failed",
                               error_message=f"A'(industry-scan) 실패: {e}")
                return

    if news_mode == "gnews":
        # ── A (GNews) 본문 생성 — fallback 또는 명시적 선택 ──
        gnews_api_key = os.environ.get("GNEWS_API_KEY", "")
        gnews = GNewsService(config, gnews_api_key)

        try:
            articles = gnews.fetch_articles()
        except Exception as e:
            logger.error("뉴스 수집 실패: %s", e)
            log_newsletter(db_conn, "daily", 0, len(recipients), "failed",
                           error_message=f"GNews 수집 실패: {e}")
            return

        inserted = insert_daily_articles(db_conn, articles)
        logger.info("DB 저장: %d건 삽입", inserted)

        # PRD 10: 기사 0건 수집 시 메시지 대체
        if not articles:
            logger.warning("수집된 기사 0건 - 대체 메시지로 발송")
            markdown_body = "※ 해당 기간 주요 신규 동향 없음"
        else:
            existing_summaries = get_existing_summaries(db_conn)
            claude_api_key = os.environ.get("CLAUDE_API_KEY", "")
            claude = ClaudeService(config, claude_api_key)

            try:
                markdown_body = claude.generate_daily(articles, existing_summaries)
            except Exception as e:
                # PRD 10: Claude 실패 시 기사 목록만 발송
                logger.error("Claude API 실패 - 기사 목록만 발송: %s", e)
                markdown_body = _fallback_articles_markdown(articles)

    # ── Step 6: Google 인증 (Gmail 발송용) ──
    creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
    token_path = str(BASE_DIR / "credentials" / "google_token.json")
    creds = get_google_credentials(creds_path, token_path)

    # ── Step 7: 마크다운 → HTML 변환 ──
    html_body = render_email_html(markdown_body, "daily", date_display)
    subject = build_email_subject("daily", date_str)

    # ── Step 8: Gmail API 발송 ──
    try:
        gmail = GmailService(creds)
        gmail.send_email(recipients, subject, html_body)
        send_status = "success"
        error_msg = None
        logger.info("이메일 발송 성공: %d명", len(recipients))
    except Exception as e:
        send_status = "failed"
        error_msg = f"Gmail 발송 실패: {e}"
        logger.error(error_msg)

    # ── Step 9: 발송 이력 기록 ──
    log_newsletter(
        db_conn,
        "daily",
        len(articles),
        len(recipients),
        send_status,
        error_message=error_msg,
    )

    # ── Step 11: 로컬 백업 ──
    _save_local_backup(markdown_body, "daily", date_str)

    # 아카이브 기사 저장
    # A 모드: GNews articles 리스트 사용. A' 모드: markdown 본문에서 URL 추출.
    if articles:
        archive_rows = [{"title": a["title"], "url": a["url"]} for a in articles]
    else:
        archive_rows = extract_article_urls(markdown_body)
        if archive_rows:
            logger.info("A' 본문에서 인용 URL %d건 추출 → archive", len(archive_rows))
    if archive_rows:
        archive_articles(db_conn, date_str, "daily", archive_rows)

    # P0(2026-05-13): 발행 결과물(.md, .csv) git 자동 commit + push.
    # push 실패는 warn만 (commit은 보존, 다음 실행에서 재전송).
    logger.info("Daily 파이프라인 완료 (status=%s)", send_status)


def run_fetch_only(config: dict, db_conn) -> None:
    """뉴스 수집만 실행 — 테스트/디버깅용."""
    logger = logging.getLogger(__name__)
    logger.info("뉴스 수집 시작 (fetch-only)")

    gnews_api_key = os.environ.get("GNEWS_API_KEY", "")
    gnews = GNewsService(config, gnews_api_key)

    try:
        articles = gnews.fetch_articles()
    except Exception as e:
        logger.error("뉴스 수집 실패: %s", e)
        return

    inserted = insert_daily_articles(db_conn, articles)
    logger.info("뉴스 수집 완료: %d건 수집, %d건 신규 삽입", len(articles), inserted)


def run_server(config: dict, db_conn) -> None:
    """웹 UI 서버 시작 (Flask)."""
    from web_ui.app import create_app

    logger = logging.getLogger(__name__)
    web_cfg = config.get("web_ui", {})
    host = web_cfg.get("host", "127.0.0.1")
    port = web_cfg.get("port", 5000)

    _try_attach_gmail(config, db_conn)

    app = create_app(config, db_conn)
    logger.info("웹 UI 서버 시작: http://%s:%d", host, port)
    app.run(host=host, port=port, debug=True)


def _fallback_articles_markdown(articles: list[dict]) -> str:
    """Claude API 실패 시 기사 목록만으로 마크다운을 생성한다 (PRD 10)."""
    lines = ["## 수집된 기사 목록\n"]
    for a in articles:
        lines.append(f"**{a['title']}**")
        if a.get("description"):
            lines.append(a["description"])
        lines.append(f"* [{a['title']}]({a['url']})\n")
    return "\n".join(lines)


def _save_local_backup(markdown: str, newsletter_type: str, date_str: str) -> None:
    """마크다운 파일을 data/newsletters/에 로컬 백업한다 (PRD 7.2 Step 11)."""
    logger = logging.getLogger(__name__)
    backup_dir = BASE_DIR / "data" / "newsletters"
    backup_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{newsletter_type}_{date_str}.md"
    filepath = backup_dir / filename
    filepath.write_text(markdown, encoding="utf-8")
    logger.info("로컬 백업 저장: %s", filepath)


def _try_attach_gmail(config: dict, db_conn) -> None:
    """``features.gmail_dedup`` 활성 시 GmailService를 db_conn에 주입.

    ``check_today_sent`` 가 Gmail Sent를 진실의 원천으로 사용해 멀티 PC
    이중 발송을 막는다. creds 로드/Gmail 초기화 실패 시 warn 로그만 남기고
    CSV fallback으로 진행 (단일 PC 환경에서도 안전).
    """
    logger = logging.getLogger(__name__)
    if not config.get("features", {}).get("gmail_dedup", True):
        logger.info("Gmail dedup 비활성 (config flag) — CSV fallback")
        return
    try:
        creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
        token_path = str(BASE_DIR / "credentials" / "google_token.json")
        creds = get_google_credentials(creds_path, token_path)
        db_conn.attach_gmail(GmailService(creds))
        logger.info("Gmail dedup 활성")
    except Exception as e:
        logger.warning("Gmail dedup 비활성 (creds/Gmail 초기화 실패: %s) — CSV fallback", e)


def main():
    parser = argparse.ArgumentParser(description="SPRi 뉴스레터 자동화 시스템")
    parser.add_argument(
        "--mode",
        choices=["daily", "server", "fetch-only"],
        required=True,
        help="실행 모드: daily(전체 파이프라인), server(웹 UI), fetch-only(뉴스 수집만)",
    )
    parser.add_argument(
        "--cron",
        action="store_true",
        default=False,
        help="cron 트리거 여부. 지정 시 멱등성 가드 활성화 (오늘 이미 발송된 경우 스킵)",
    )
    args = parser.parse_args()

    # 환경변수 로드
    load_dotenv(BASE_DIR / ".env")

    # 설정 로드
    config = load_config()

    # 로깅 설정
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("SPRi 뉴스레터 시스템 시작 (mode=%s)", args.mode)

    # DB 초기화 (로컬 CSV)
    data_dir = BASE_DIR / "data" / "db"
    db_conn = init_db(data_dir)

    try:
        if args.mode == "daily":
            run_daily_pipeline(config, db_conn, cron=args.cron)
        elif args.mode == "fetch-only":
            run_fetch_only(config, db_conn)
        elif args.mode == "server":
            run_server(config, db_conn)
    finally:
        db_conn.close()
        logger.info("시스템 종료")


if __name__ == "__main__":
    main()
