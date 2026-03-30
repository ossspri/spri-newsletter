"""web_ui/app.py — Flask 웹 UI (Daily + Weekly 탭 통합)

PRD 8: 전문가용 로컬 웹 UI.
Daily 탭: 뉴스 수집 → 생성 → 미리보기 → 발송 3단계
Weekly 탭: 기사 선택(N/25) → 생성 → 발송
"""
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, g, render_template, request, jsonify, redirect, url_for

from src.db import (
    insert_daily_articles,
    get_existing_summaries,
    get_weekly_articles,
    check_today_sent,
    log_newsletter,
    archive_articles,
    insert_manual_article,
)
from src.news_service import GNewsService
from src.claude_service import ClaudeService
from src.email_template import render_email_html, build_email_subject
from src.gmail_service import GmailService
from src.drive_service import DriveService
from src.google_auth import get_google_credentials
from src.utils import get_kst_date_str, get_kst_display_date

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent


def extract_url_metadata(url: str) -> dict:
    """URL에서 메타데이터(제목, 설명)를 추출한다.

    beautifulsoup4를 사용하여 og:title, og:description 또는 <title> 태그를 추출.
    """
    import requests
    from bs4 import BeautifulSoup

    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SPRi-Newsletter/1.0)"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # og:title 우선, 없으면 <title>
        og_title = soup.find("meta", property="og:title")
        title = og_title["content"] if og_title else ""
        if not title:
            title_tag = soup.find("title")
            title = title_tag.string.strip() if title_tag and title_tag.string else url

        # og:description 우선, 없으면 meta description
        og_desc = soup.find("meta", property="og:description")
        description = og_desc["content"] if og_desc else ""
        if not description:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            description = meta_desc["content"] if meta_desc else ""

        return {"title": title, "description": description}
    except Exception as e:
        logger.warning("URL 메타데이터 추출 실패: %s — %s", url, e)
        return {"title": url, "description": ""}


def create_app(config: dict, db_conn: sqlite3.Connection) -> Flask:
    """Flask 앱을 생성한다.

    Args:
        config: config.yaml 설정 dict
        db_conn: SQLite DB 연결

    Returns:
        Flask 앱 인스턴스
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["config"] = config

    # DB 경로 추출 — :memory: 또는 파일 경로
    db_path = db_conn.execute("PRAGMA database_list").fetchone()[2]
    is_memory = not db_path  # :memory: DB는 빈 문자열 반환

    if is_memory:
        # 테스트 환경: 인메모리 DB를 직접 공유 (스레드 안전성은 테스트에서 단일 스레드)
        app.config["db_conn"] = db_conn
    else:
        app.config["db_path"] = db_path

    def get_db():
        """요청마다 DB 연결을 반환한다."""
        if is_memory:
            return app.config["db_conn"]
        if "db_conn" not in g:
            g.db_conn = sqlite3.connect(app.config["db_path"])
            g.db_conn.execute("PRAGMA journal_mode=WAL")
        return g.db_conn

    @app.teardown_appcontext
    def close_db(exc):
        if not is_memory:
            conn = g.pop("db_conn", None)
            if conn is not None:
                conn.close()

    def get_cfg():
        return app.config["config"]

    # ── 루트 ──

    @app.route("/")
    def index():
        return redirect(url_for("daily_page"))

    # ── Daily 탭 ──

    @app.route("/daily")
    def daily_page():
        conn = get_db()
        today = datetime.now().strftime("%Y-%m-%d")
        # 오늘 수집된 기사
        cursor = conn.execute(
            "SELECT id, title, url, description, source_name, published_at "
            "FROM daily_articles WHERE collected_at LIKE ? ORDER BY published_at DESC",
            (f"{today}%",),
        )
        articles = [
            {"id": r[0], "title": r[1], "url": r[2], "description": r[3],
             "source_name": r[4], "published_at": r[5]}
            for r in cursor.fetchall()
        ]
        sent_today = check_today_sent(conn, "daily")
        return render_template("daily.html", articles=articles, sent_today=sent_today)

    @app.route("/daily/fetch", methods=["POST"])
    def daily_fetch():
        """GNews API로 뉴스를 수집한다."""
        try:
            gnews_api_key = os.environ.get("GNEWS_API_KEY", "")
            gnews = GNewsService(get_cfg(), gnews_api_key)
            articles = gnews.fetch_articles()
            inserted = insert_daily_articles(get_db(), articles)
            return jsonify({
                "success": True,
                "count": len(articles),
                "inserted": inserted,
                "articles": articles,
            })
        except Exception as e:
            logger.error("뉴스 수집 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/daily/generate", methods=["POST"])
    def daily_generate():
        """Claude API로 Daily 뉴스레터를 생성한다."""
        try:
            conn = get_db()
            today = datetime.now().strftime("%Y-%m-%d")
            cursor = conn.execute(
                "SELECT title, url, description, source_name, published_at "
                "FROM daily_articles WHERE collected_at LIKE ? ORDER BY published_at DESC",
                (f"{today}%",),
            )
            articles = [
                {"title": r[0], "url": r[1], "description": r[2],
                 "source_name": r[3], "published_at": r[4]}
                for r in cursor.fetchall()
            ]

            if not articles:
                return jsonify({
                    "success": False,
                    "error": "수집된 기사가 없습니다. 먼저 뉴스를 수집하세요.",
                }), 400

            existing_summaries = get_existing_summaries(conn)
            claude_api_key = os.environ.get("CLAUDE_API_KEY", "")
            claude = ClaudeService(get_cfg(), claude_api_key)
            markdown = claude.generate_daily(articles, existing_summaries)

            date_display = get_kst_display_date()
            html_preview = render_email_html(markdown, "daily", date_display)

            return jsonify({
                "success": True,
                "markdown": markdown,
                "html_preview": html_preview,
            })
        except Exception as e:
            logger.error("뉴스레터 생성 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/daily/send", methods=["POST"])
    def daily_send():
        """Daily 이메일을 발송한다."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        try:
            cfg = get_cfg()
            date_str = get_kst_date_str()
            date_display = get_kst_display_date()
            recipients = cfg.get("recipients", {}).get("daily", [])

            html_body = render_email_html(markdown, "daily", date_display)
            subject = build_email_subject("daily", date_str)

            creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
            token_path = str(BASE_DIR / "credentials" / "google_token.json")
            creds = get_google_credentials(creds_path, token_path)
            gmail = GmailService(creds)
            gmail.send_email(recipients, subject, html_body)

            log_newsletter(get_db(), "daily", 0, len(recipients), "success")

            return jsonify({
                "success": True,
                "recipients": len(recipients),
            })
        except Exception as e:
            logger.error("이메일 발송 실패: %s", e)
            log_newsletter(get_db(), "daily", 0, 0, "failed",
                           error_message=str(e))
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/daily/save-drive", methods=["POST"])
    def daily_save_drive():
        """Daily 뉴스레터를 Google Drive에 저장한다."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        try:
            cfg = get_cfg()
            date_str = get_kst_date_str()
            folder_id = cfg.get("drive", {}).get("folder_id", "")

            creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
            token_path = str(BASE_DIR / "credentials" / "google_token.json")
            creds = get_google_credentials(creds_path, token_path)
            drive = DriveService(creds)
            doc_id = drive.create_document(markdown, "daily", date_str, folder_id)

            return jsonify({"success": True, "doc_id": doc_id})
        except Exception as e:
            logger.error("Drive 저장 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ── Weekly 탭 ──

    @app.route("/weekly")
    def weekly_page():
        conn = get_db()
        articles = get_weekly_articles(conn, days=7)
        # 날짜별 그룹핑
        grouped = {}
        for a in articles:
            date_key = a["published_at"][:10] if a["published_at"] else "unknown"
            grouped.setdefault(date_key, []).append(a)
        # 수동 추가 기사
        cursor = conn.execute(
            "SELECT id, title, url, description FROM manual_articles ORDER BY added_at DESC"
        )
        manual_articles = [
            {"id": r[0], "title": r[1], "url": r[2], "description": r[3]}
            for r in cursor.fetchall()
        ]
        return render_template(
            "weekly.html",
            grouped_articles=grouped,
            manual_articles=manual_articles,
            total_count=len(articles) + len(manual_articles),
        )

    @app.route("/weekly/add-article", methods=["POST"])
    def weekly_add_article():
        """수동 기사를 추가한다 (URL → 자동 메타 추출)."""
        data = request.get_json() or {}
        url = data.get("url", "").strip()
        if not url:
            return jsonify({"success": False, "error": "URL이 필요합니다."}), 400

        meta = extract_url_metadata(url)
        title = data.get("title") or meta["title"]
        description = data.get("description") or meta["description"]

        inserted = insert_manual_article(get_db(), title, url, description)
        if not inserted:
            return jsonify({"success": False, "error": "이미 추가된 URL입니다."}), 409

        return jsonify({
            "success": True,
            "article": {"title": title, "url": url, "description": description},
        })

    @app.route("/weekly/generate", methods=["POST"])
    def weekly_generate():
        """Claude API로 Weekly 보고서를 생성한다."""
        data = request.get_json() or {}
        articles = data.get("articles", [])

        if not articles:
            return jsonify({
                "success": False,
                "error": "선택된 기사가 없습니다.",
            }), 400

        try:
            existing_summaries = get_existing_summaries(get_db())
            claude_api_key = os.environ.get("CLAUDE_API_KEY", "")
            claude = ClaudeService(get_cfg(), claude_api_key)
            markdown = claude.generate_weekly(articles, existing_summaries)

            date_display = get_kst_display_date()
            html_preview = render_email_html(markdown, "weekly", date_display)

            return jsonify({
                "success": True,
                "markdown": markdown,
                "html_preview": html_preview,
            })
        except Exception as e:
            logger.error("주간 보고서 생성 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/weekly/send", methods=["POST"])
    def weekly_send():
        """Weekly 이메일을 발송한다."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        try:
            cfg = get_cfg()
            date_str = get_kst_date_str()
            date_display = get_kst_display_date()
            recipients = cfg.get("recipients", {}).get("weekly", [])

            html_body = render_email_html(markdown, "weekly", date_display)
            subject = build_email_subject("weekly", date_str)

            creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
            token_path = str(BASE_DIR / "credentials" / "google_token.json")
            creds = get_google_credentials(creds_path, token_path)
            gmail = GmailService(creds)
            gmail.send_email(recipients, subject, html_body)

            log_newsletter(get_db(), "weekly", 0, len(recipients), "success")

            return jsonify({"success": True, "recipients": len(recipients)})
        except Exception as e:
            logger.error("주간 이메일 발송 실패: %s", e)
            log_newsletter(get_db(), "weekly", 0, 0, "failed",
                           error_message=str(e))
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/weekly/save-drive", methods=["POST"])
    def weekly_save_drive():
        """Weekly 보고서를 Google Drive에 저장한다."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        try:
            cfg = get_cfg()
            date_str = get_kst_date_str()
            folder_id = cfg.get("drive", {}).get("folder_id", "")

            creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
            token_path = str(BASE_DIR / "credentials" / "google_token.json")
            creds = get_google_credentials(creds_path, token_path)
            drive = DriveService(creds)
            doc_id = drive.create_document(markdown, "weekly", date_str, folder_id)

            return jsonify({"success": True, "doc_id": doc_id})
        except Exception as e:
            logger.error("Weekly Drive 저장 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    # ── 공통 ──

    @app.route("/preview", methods=["POST"])
    def preview():
        """마크다운을 SPRi 브랜딩 HTML로 미리보기 변환한다."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        newsletter_type = data.get("type", "daily")
        date_display = get_kst_display_date()

        html = render_email_html(markdown, newsletter_type, date_display)
        return jsonify({"success": True, "html": html})

    return app
