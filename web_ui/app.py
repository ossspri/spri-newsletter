"""web_ui/app.py — Flask 웹 UI (Daily + Weekly 탭 통합)

PRD 8: 전문가용 로컬 웹 UI.
Daily 탭: 뉴스 수집 → 생성 → 미리보기 → 발간(이메일+Drive+NotebookLM) 3단계
Weekly 탭: 기사 선택(N/25) → 생성 → 발간(이메일+Drive+NotebookLM+로컬백업)
"""
import logging
import os
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for

from src.db import (
    insert_daily_articles,
    get_existing_summaries,
    get_weekly_articles,
    check_today_sent,
    log_newsletter,
    archive_articles,
    insert_manual_article,
    get_daily_articles_today,
    get_all_manual_articles,
    clear_today_archive,
    clear_today_daily_articles,
    clear_all_manual_articles,
)
from src.news_service import GNewsService
from src.claude_service import ClaudeService
from src.email_template import render_email_html, build_email_subject
from src.gmail_service import GmailService
from src.drive_service import DriveService
from src.notebooklm_service import (
    NotebookLMService, check_nlm_auth, reauth_nlm_open, reauth_nlm_save,
)
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


def create_app(config: dict, db_conn) -> Flask:
    """Flask 앱을 생성한다.

    Args:
        config: config.yaml 설정 dict
        db_conn: SheetsDB 인스턴스

    Returns:
        Flask 앱 인스턴스
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["config"] = config
    app.config["db_conn"] = db_conn

    def get_db():
        return app.config["db_conn"]

    def get_cfg():
        return app.config["config"]

    # ── 루트 ──

    @app.route("/")
    def index():
        return redirect(url_for("daily_page"))

    # ── Daily 탭 ──

    @app.route("/daily")
    def daily_page():
        db = get_db()
        articles = get_daily_articles_today(db)
        sent_today = check_today_sent(db, "daily")
        return render_template("daily.html", articles=articles, sent_today=sent_today)

    @app.route("/daily/preview-keywords", methods=["POST"])
    def daily_preview_keywords():
        """GNews 검색에 사용될 키워드 목록을 반환한다."""
        cfg = get_cfg()
        queries = cfg.get("gnews", {}).get("queries", [])
        return jsonify({"success": True, "queries": queries})

    @app.route("/daily/preview-articles", methods=["POST"])
    def daily_preview_articles():
        """GNews API로 기사를 검색하여 미리보기를 반환한다 (DB 저장 안 함)."""
        try:
            cfg = get_cfg()
            data = request.get_json() or {}
            custom_queries = data.get("queries")

            gnews_api_key = os.environ.get("GNEWS_API_KEY", "")
            gnews = GNewsService(cfg, gnews_api_key)

            # 사용자가 키워드를 수정한 경우 반영
            if custom_queries is not None:
                gnews.queries = custom_queries

            queries = gnews.queries
            articles = gnews.fetch_articles()

            return jsonify({
                "success": True,
                "queries": queries,
                "count": len(articles),
                "articles": articles,
            })
        except Exception as e:
            logger.error("기사 미리보기 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/daily/fetch", methods=["POST"])
    def daily_fetch():
        """GNews API로 뉴스를 수집한다.

        요청 body에 articles가 포함되면 해당 기사를 직접 저장하고,
        없으면 GNews API를 호출하여 수집한다.
        """
        try:
            data = request.get_json() or {}
            prefetched = data.get("articles")

            if prefetched:
                articles = prefetched
            else:
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
            db = get_db()
            articles = get_daily_articles_today(db)

            if not articles:
                return jsonify({
                    "success": False,
                    "error": "수집된 기사가 없습니다. 먼저 뉴스를 수집하세요.",
                }), 400

            existing_summaries = get_existing_summaries(db)
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

    @app.route("/daily/publish", methods=["POST"])
    def daily_publish():
        """Daily 뉴스레터를 발간한다 (이메일 발송 → Drive 저장 → NotebookLM 저장)."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        cfg = get_cfg()
        db = get_db()
        date_str = get_kst_date_str()
        date_display = get_kst_display_date()
        creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
        token_path = str(BASE_DIR / "credentials" / "google_token.json")
        results = {"email": None, "drive": None, "notebooklm": None}

        # ── Step 3: Google Drive 저장 (이메일 링크 포함을 위해 선행) ──
        drive_doc_id = None
        drive_doc_url = ""
        try:
            folder_id = cfg.get("drive", {}).get("folder_id", "")
            creds = get_google_credentials(creds_path, token_path)
            drive = DriveService(creds)
            drive_doc_id = drive.create_document(markdown, "daily", date_str, folder_id)
            drive_doc_url = f"https://docs.google.com/document/d/{drive_doc_id}/edit"
            results["drive"] = {"success": True, "doc_id": drive_doc_id}
            logger.info("Drive 저장 완료: %s", drive_doc_id)
        except Exception as e:
            logger.error("Drive 저장 실패 (계속 진행): %s", e)
            results["drive"] = {"success": False, "error": str(e)}

        # ── Step 4: Gmail 발송 ──
        try:
            recipients = cfg.get("recipients", {}).get("daily", [])
            html_body = render_email_html(markdown, "daily", date_display, drive_doc_url)
            subject = build_email_subject("daily", date_str)

            creds = get_google_credentials(creds_path, token_path)
            gmail = GmailService(creds)
            gmail.send_email(recipients, subject, html_body)
            results["email"] = {"success": True, "recipients": len(recipients)}
            logger.info("이메일 발송 완료 (%d명)", len(recipients))
        except Exception as e:
            logger.error("이메일 발송 실패: %s", e)
            log_newsletter(db, "daily", 0, 0, "failed", error_message=str(e))
            return jsonify({
                "success": False,
                "error": f"이메일 발송 실패: {e}",
                "results": results,
            }), 500

        # Daily는 NotebookLM 저장 생략 (Weekly 발간 시 저장)
        nlm_notebook = None

        # ── 발송 이력 기록 ──
        log_newsletter(
            db, "daily", 0, len(recipients), "success",
            drive_doc_id=drive_doc_id, nlm_notebook=nlm_notebook,
        )

        return jsonify({"success": True, "results": results})

    # ── Weekly 탭 ──

    @app.route("/weekly")
    def weekly_page():
        db = get_db()
        articles = get_weekly_articles(db, days=7)
        # 날짜별 그룹핑
        grouped = {}
        for a in articles:
            pub = str(a.get("published_at", ""))
            date_key = pub[:10] if pub else "unknown"
            grouped.setdefault(date_key, []).append(a)
        # 수동 추가 기사
        manual_articles = get_all_manual_articles(db)
        return render_template(
            "weekly.html",
            grouped_articles=grouped,
            manual_articles=manual_articles,
            total_count=len(articles) + len(manual_articles),
        )

    @app.route("/weekly/translate-articles", methods=["POST"])
    def weekly_translate_articles():
        """선택된 기사의 제목/설명을 한국어로 번역한다."""
        data = request.get_json() or {}
        articles = data.get("articles", [])
        if not articles:
            return jsonify({"success": False, "error": "번역할 기사가 없습니다."}), 400

        try:
            claude_api_key = os.environ.get("CLAUDE_API_KEY", "")
            claude = ClaudeService(get_cfg(), claude_api_key)
            translated = claude.translate_articles(articles)
            return jsonify({"success": True, "articles": translated})
        except Exception as e:
            logger.error("기사 번역 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

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

    @app.route("/weekly/publish", methods=["POST"])
    def weekly_publish():
        """Weekly 보고서를 발간한다 (이메일 발송 → Drive 저장 → NotebookLM → 로컬 백업)."""
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        cfg = get_cfg()
        db = get_db()
        date_str = get_kst_date_str()
        date_display = get_kst_display_date()
        creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
        token_path = str(BASE_DIR / "credentials" / "google_token.json")
        results = {"email": None, "drive": None, "notebooklm": None, "backup": None}

        # ── Step 3: Google Drive 저장 (이메일 링크 포함을 위해 선행) ──
        drive_doc_id = None
        drive_doc_url = ""
        try:
            folder_id = cfg.get("drive", {}).get("folder_id", "")
            creds = get_google_credentials(creds_path, token_path)
            drive = DriveService(creds)
            drive_doc_id = drive.create_document(markdown, "weekly", date_str, folder_id)
            drive_doc_url = f"https://docs.google.com/document/d/{drive_doc_id}/edit"
            results["drive"] = {"success": True, "doc_id": drive_doc_id}
            logger.info("Weekly Drive 저장 완료: %s", drive_doc_id)
        except Exception as e:
            logger.error("Weekly Drive 저장 실패 (계속 진행): %s", e)
            results["drive"] = {"success": False, "error": str(e)}

        # ── Step 4: Gmail 발송 ──
        try:
            recipients = cfg.get("recipients", {}).get("weekly", [])
            html_body = render_email_html(markdown, "weekly", date_display, drive_doc_url)
            subject = build_email_subject("weekly", date_str)

            creds = get_google_credentials(creds_path, token_path)
            gmail = GmailService(creds)
            gmail.send_email(recipients, subject, html_body)
            results["email"] = {"success": True, "recipients": len(recipients)}
            logger.info("주간 이메일 발송 완료 (%d명)", len(recipients))
        except Exception as e:
            logger.error("주간 이메일 발송 실패: %s", e)
            log_newsletter(db, "weekly", 0, 0, "failed", error_message=str(e))
            return jsonify({
                "success": False,
                "error": f"이메일 발송 실패: {e}",
                "results": results,
            }), 500

        # ── Step 5: NotebookLM 저장 + 로컬 백업 (사전 인증 체크) ──
        nlm_notebook = None
        auth_status = check_nlm_auth()
        if not auth_status["valid"]:
            logger.warning("NotebookLM 인증 만료, 건너뜀: %s", auth_status["reason"])
            results["notebooklm"] = {"success": False, "error": auth_status["reason"],
                                     "skipped": True}
        else:
            try:
                articles = get_weekly_articles(db, days=7)
                manual = get_all_manual_articles(db)
                all_articles = articles + manual
                if all_articles:
                    nlm = NotebookLMService(cfg)
                    nlm_notebook = nlm.save_sources(
                        date_str,
                        [{"title": a["title"], "url": a["url"]} for a in all_articles],
                        markdown,
                    )
                    results["notebooklm"] = {"success": True, "notebook_id": nlm_notebook}
                    logger.info("Weekly NotebookLM 저장 완료: %s (수동 %d건 포함)",
                                nlm_notebook, len(manual))
                else:
                    results["notebooklm"] = {"success": True, "notebook_id": None}
                    logger.info("Weekly NotebookLM 건너뜀: 기사 없음")
            except Exception as e:
                logger.error("Weekly NotebookLM 저장 실패 (계속 진행): %s", e)
                results["notebooklm"] = {"success": False, "error": str(e)}

        # 로컬 마크다운 백업
        try:
            backup_dir = BASE_DIR / "data" / "newsletters"
            backup_dir.mkdir(parents=True, exist_ok=True)
            filepath = backup_dir / f"weekly_{date_str}.md"
            filepath.write_text(markdown, encoding="utf-8")
            results["backup"] = {"success": True, "path": str(filepath)}
            logger.info("Weekly 로컬 백업 저장: %s", filepath)
        except Exception as e:
            logger.error("Weekly 로컬 백업 실패 (계속 진행): %s", e)
            results["backup"] = {"success": False, "error": str(e)}

        # ── 발송 이력 기록 ──
        log_newsletter(
            db, "weekly", 0, len(recipients), "success",
            drive_doc_id=drive_doc_id, nlm_notebook=nlm_notebook,
        )

        return jsonify({"success": True, "results": results})

    # ── 공통 ──

    @app.route("/reset-today", methods=["POST"])
    def reset_today():
        """오늘 날짜의 기사·아카이브·백업·NotebookLM 소스를 초기화한다 (수동 테스트용).

        발송 이력(newsletter_log)은 보존한다.
        """
        try:
            db = get_db()
            cfg = get_cfg()
            date_str = get_kst_date_str()

            # article_archive에서 오늘 데이터 삭제
            archive_deleted = clear_today_archive(db, date_str)

            # daily_articles에서 오늘 수집 기사 삭제
            daily_deleted = clear_today_daily_articles(db, date_str)

            # manual_articles 전체 삭제
            manual_deleted = clear_all_manual_articles(db)

            # 로컬 백업 파일 삭제
            backup_dir = BASE_DIR / "data" / "newsletters"
            files_deleted = []
            for pattern in [f"daily_{date_str}.md", f"weekly_{date_str}.md"]:
                filepath = backup_dir / pattern
                if filepath.exists():
                    filepath.unlink()
                    files_deleted.append(pattern)

            # NotebookLM 소스 삭제
            nlm_result = {"deleted_count": 0}
            try:
                nlm = NotebookLMService(cfg)
                nlm_result = nlm.delete_today_sources(date_str)
            except Exception as e:
                logger.error("NotebookLM 소스 삭제 실패 (계속 진행): %s", e)
                nlm_result = {"deleted_count": 0, "error": str(e)}

            logger.info(
                "테스트 초기화 완료: 아카이브 %d건, daily %d건, manual %d건, "
                "파일 %s, NotebookLM %d건",
                archive_deleted, daily_deleted, manual_deleted,
                files_deleted, nlm_result["deleted_count"],
            )
            return jsonify({
                "success": True,
                "date": date_str,
                "archive_deleted": archive_deleted,
                "daily_deleted": daily_deleted,
                "manual_deleted": manual_deleted,
                "files_deleted": files_deleted,
                "nlm_deleted": nlm_result["deleted_count"],
            })
        except Exception as e:
            logger.error("테스트 초기화 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/nlm/status")
    def nlm_status():
        """NotebookLM 인증 상태를 반환한다."""
        try:
            result = check_nlm_auth()
            return jsonify({"success": True, **result})
        except Exception as e:
            logger.error("NotebookLM 인증 체크 실패: %s", e)
            return jsonify({"success": True, "valid": False,
                            "reason": f"체크 실패: {e}",
                            "login_date": None, "expires_in_hours": None})

    @app.route("/nlm/reauth/open", methods=["POST"])
    def nlm_reauth_open():
        """NotebookLM 재인증 브라우저를 연다."""
        result = reauth_nlm_open()
        return jsonify(result)

    @app.route("/nlm/reauth/save", methods=["POST"])
    def nlm_reauth_save():
        """NotebookLM 재인증 브라우저에서 쿠키를 저장하고 닫는다."""
        result = reauth_nlm_save()
        return jsonify(result)

    @app.route("/nlm/save", methods=["POST"])
    def nlm_save_weekly():
        """Weekly 기사를 NotebookLM에 저장한다 (재인증 후 재시도용)."""
        try:
            db = get_db()
            cfg = get_cfg()
            date_str = get_kst_date_str()
            data = request.get_json() or {}
            markdown = data.get("markdown", "")

            articles = get_weekly_articles(db, days=7)
            manual = get_all_manual_articles(db)
            all_articles = articles + manual
            if not all_articles:
                return jsonify({"success": True, "notebook_id": None})

            nlm = NotebookLMService(cfg)
            notebook_id = nlm.save_sources(
                date_str,
                [{"title": a["title"], "url": a["url"]} for a in all_articles],
                markdown,
            )
            logger.info("NotebookLM 재시도 저장 완료: %s", notebook_id)
            return jsonify({"success": True, "notebook_id": notebook_id})
        except Exception as e:
            logger.error("NotebookLM 재시도 저장 실패: %s", e)
            return jsonify({"success": False, "error": str(e)})

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
