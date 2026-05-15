"""web_ui/app.py — Flask 웹 UI (Daily + Weekly + Focus 3탭)

전문가용 로컬 웹 UI. 2026-05-15 Drive/NotebookLM 통합 제거 (로컬+git 공유 방향).
Daily 탭: 뉴스 수집 → 생성 → 미리보기 → 발간(Gmail 발송)
Weekly 탭: 자동 daily 기사 선택 → 생성 → 발간 (표준)
Focus 탭: 수동 기사·보고서·전문가 인사이트·편집 미리보기 → 발간 (큐레이션)
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
    insert_manual_report,
    get_daily_articles_today,
    get_all_manual_articles,
    get_all_manual_reports,
    get_manual_report,
    clear_today_archive,
    clear_today_daily_articles,
    clear_all_manual_articles,
    delete_manual_article,
    delete_manual_report,
)
from src.manual_reports import (
    MANUAL_REPORTS_DIR,
    detect_url_kind,
    download_pdf,
    extract_pdf_text,
    is_safe_url,
    sanitize_filename,
    save_report_text,
)
from src.news_service import GNewsService
from src.claude_service import ClaudeService
from src.email_template import render_email_html, build_email_subject
from src.gmail_service import GmailService
from src.git_sync import GitSync, GitSyncError
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
    # PR2: 수동 보고서 PDF 업로드 — 50MB 제한 (초과 시 413).
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

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
        """Daily 뉴스레터를 발간한다 (Gmail 발송 → 로그 기록)."""
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
        results = {"email": None, "git_sync": None}

        # P0(2026-05-13): publish 직전 git pull. 충돌 시 발송 차단.
        git_sync = GitSync(BASE_DIR, cfg)
        try:
            git_sync.pull_or_fail()
        except GitSyncError as e:
            logger.error("git_sync pull 실패 — Daily 발송 차단: %s", e)
            return jsonify({
                "success": False,
                "error": f"git_sync pull 실패 (수동 해결 필요): {e}",
            }), 409

        # ── Step 4: Gmail 발송 ──
        try:
            recipients = cfg.get("recipients", {}).get("daily", [])
            html_body = render_email_html(markdown, "daily", date_display)
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

        # ── 발송 이력 기록 ──
        log_newsletter(db, "daily", 0, len(recipients), "success")

        # P0(2026-05-13): data/ 변경분 git commit + push. push 실패는 warn만.
        try:
            results["git_sync"] = git_sync.commit_and_push("daily", date_str)
        except Exception as e:
            logger.warning("git_sync commit/push 예외 (발송은 완료): %s", e)
            results["git_sync"] = {"committed": False, "pushed": False,
                                   "skipped": "exception", "error": str(e)}

        return jsonify({"success": True, "results": results})

    # ── Weekly 탭 (자동 수집 daily 기사만) ──

    @app.route("/weekly")
    def weekly_page():
        """Weekly 표준 보고서 — 자동 수집 daily 기사 7일치만 선택해서 발간.

        2026-05-15 분리: 수동 기사·보고서·전문가 인사이트·편집 미리보기는
        Focus 탭으로 이동. Weekly는 단순·표준 흐름 (5a62540 시점 형태).
        """
        db = get_db()
        articles = get_weekly_articles(db, days=7)
        # 날짜별 그룹핑 (5a62540 패턴).
        grouped: dict[str, list[dict]] = {}
        for a in articles:
            pub = str(a.get("published_at", ""))
            date_key = pub[:10] if pub else "unknown"
            grouped.setdefault(date_key, []).append(a)
        return render_template(
            "weekly.html",
            grouped_articles=grouped,
            total_count=len(articles),
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

    @app.route("/weekly/generate", methods=["POST"])
    def weekly_generate():
        """Claude API로 Weekly 표준 보고서를 생성한다 (자동 수집 기사만)."""
        data = request.get_json() or {}
        articles = data.get("articles", [])

        if not articles:
            return jsonify({
                "success": False,
                "error": "선택된 기사가 없습니다.",
            }), 400

        try:
            db = get_db()
            existing_summaries = get_existing_summaries(db)

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
        """Weekly 표준 보고서를 발간한다 (Gmail 발송 → 로컬 백업).

        2026-05-15 Drive/NotebookLM 통합 제거. Gmail 발송 + 로컬 .md 백업만.
        """
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
        results = {"email": None, "backup": None, "git_sync": None}

        # P0(2026-05-13): publish 직전 git pull. 충돌 시 발송 차단.
        git_sync = GitSync(BASE_DIR, cfg)
        try:
            git_sync.pull_or_fail()
        except GitSyncError as e:
            logger.error("git_sync pull 실패 — Weekly 발송 차단: %s", e)
            return jsonify({
                "success": False,
                "error": f"git_sync pull 실패 (수동 해결 필요): {e}",
            }), 409

        # ── Step 4: Gmail 발송 ──
        try:
            recipients = cfg.get("recipients", {}).get("weekly", [])
            html_body = render_email_html(markdown, "weekly", date_display)
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
        log_newsletter(db, "weekly", 0, len(recipients), "success")

        # P0(2026-05-13): data/ 변경분 git commit + push. push 실패는 warn만.
        try:
            results["git_sync"] = git_sync.commit_and_push("weekly", date_str)
        except Exception as e:
            logger.warning("git_sync commit/push 예외 (발송은 완료): %s", e)
            results["git_sync"] = {"committed": False, "pushed": False,
                                   "skipped": "exception", "error": str(e)}

        return jsonify({"success": True, "results": results})

    # ── Focus 탭 ──

    @app.route("/focus")
    def focus_page():
        db = get_db()
        articles = get_weekly_articles(db, days=7)
        # 수동 추가 기사
        manual_articles = get_all_manual_articles(db)
        # 수동 추가 보고서 (PR3)
        manual_reports = get_all_manual_reports(db)
        return render_template(
            "focus.html",
            weekly_articles=articles,  # 출처 그룹 없이 단일 list (1.3 수정)
            manual_articles=manual_articles,
            manual_reports=manual_reports,
            total_count=len(articles) + len(manual_articles),
        )

    @app.route("/focus/translate-articles", methods=["POST"])
    def focus_translate_articles():
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

    @app.route("/focus/add-article", methods=["POST"])
    def focus_add_article():
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

        new_id = ""
        for r in get_all_manual_articles(get_db()):
            if str(r.get("url", "")) == url:
                new_id = str(r.get("id", ""))
                break

        return jsonify({
            "success": True,
            "article": {"id": new_id, "title": title, "url": url, "description": description},
        })

    @app.route("/focus/add-report", methods=["POST"])
    def focus_add_report():
        """수동 보고서를 추가한다.

        두 가지 입력 형태:
          - multipart/form-data + ``file`` 필드 → PDF 업로드
          - multipart/form-data + ``url`` 필드 → URL (HTML 또는 PDF 직링크)

        흐름:
          1. URL이면 ``is_safe_url`` SSRF 검증 → ``detect_url_kind``로 분기
          2. HTML: ``extract_url_metadata`` 재사용해 title/description
             확보 → summary는 description으로 폴백
          3. PDF: ``download_pdf`` (또는 업로드 파일을 그대로 저장) →
             ``extract_pdf_text`` → ``ClaudeService.summarize_report_text``
          4. 본문 전문을 ``data/manual_reports/{id}.txt``로 저장
          5. ``insert_manual_report``로 메타 row 기록

        실패 정책: Claude 요약 실패해도 head_excerpt만 가지고 진행 (보고서
        추가 자체는 성공). PDF 추출이 빈 문자열(이미지 스캔)이면 경고 메시지
        포함해 응답.
        """
        from src.db import _gen_id
        from io import BytesIO

        url = (request.form.get("url") or "").strip()
        upload = request.files.get("file")

        if not url and not upload:
            return jsonify({"success": False, "error": "url 또는 file 중 하나는 필수입니다."}), 400

        report_id = _gen_id()
        title = ""
        summary = ""
        full_text = ""
        head_excerpt = ""
        source_type = ""
        original_filename = ""
        file_path_str = ""
        text_path_str = ""
        warning = None

        try:
            if upload:
                # ── PDF 파일 업로드 분기 ──
                source_type = "pdf"
                raw_name = upload.filename or "unnamed.pdf"
                original_filename = sanitize_filename(raw_name)
                if not original_filename.lower().endswith(".pdf"):
                    return jsonify({"success": False, "error": "PDF 파일만 업로드 가능합니다."}), 400

                # Magic byte 검증을 위해 첫 청크만 미리 읽기
                first = upload.stream.read(8)
                if not first.startswith(b"%PDF-"):
                    return jsonify({"success": False, "error": "유효한 PDF 파일이 아닙니다."}), 400

                pdf_path = MANUAL_REPORTS_DIR / f"{report_id}.pdf"
                pdf_path.parent.mkdir(parents=True, exist_ok=True)
                with pdf_path.open("wb") as f:
                    f.write(first)
                    while True:
                        chunk = upload.stream.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                file_path_str = str(pdf_path)

                full_text, head_excerpt = extract_pdf_text(pdf_path)
                if not full_text:
                    warning = "PDF에서 텍스트를 추출하지 못했습니다 (이미지 스캔본일 수 있음)."
                title = original_filename.removesuffix(".pdf")

            else:
                # ── URL 입력 분기 ──
                if not is_safe_url(url):
                    return jsonify({"success": False, "error": "안전하지 않은 URL입니다."}), 400

                kind = detect_url_kind(url)
                if kind == "pdf":
                    source_type = "pdf"
                    pdf_path = MANUAL_REPORTS_DIR / f"{report_id}.pdf"
                    try:
                        download_pdf(url, pdf_path)
                    except ValueError as ve:
                        return jsonify({"success": False, "error": str(ve)}), 400
                    file_path_str = str(pdf_path)
                    # URL의 마지막 path segment를 원본 파일명으로
                    from urllib.parse import urlparse as _up
                    original_filename = sanitize_filename(Path(_up(url).path).name or "downloaded.pdf")
                    full_text, head_excerpt = extract_pdf_text(pdf_path)
                    if not full_text:
                        warning = "PDF에서 텍스트를 추출하지 못했습니다."
                    title = original_filename.removesuffix(".pdf")
                else:
                    # HTML 페이지
                    source_type = "url"
                    meta = extract_url_metadata(url)
                    title = meta["title"] or url
                    full_text = meta.get("description", "") or ""
                    head_excerpt = full_text
                    summary = full_text  # 짧은 메타는 그대로 요약으로 사용

            # ── Claude 요약 (PDF 본문이 충분히 길 때만) ──
            if full_text and source_type == "pdf":
                claude_api_key = os.environ.get("CLAUDE_API_KEY", "")
                if claude_api_key:
                    try:
                        claude = ClaudeService(get_cfg(), claude_api_key)
                        summary = claude.summarize_report_text(full_text)
                    except Exception as e:
                        logger.warning("보고서 요약 실패, head_excerpt만 사용: %s", e)
                        summary = head_excerpt[:1500]
                else:
                    summary = head_excerpt[:1500]

            # ── 전문 저장 ──
            if full_text:
                text_path = save_report_text(report_id, full_text)
                text_path_str = str(text_path)

            # ── DB 메타 기록 ──
            insert_manual_report(
                get_db(),
                report_id=report_id,
                title=title,
                source_type=source_type,
                url=url if source_type == "url" or (source_type == "pdf" and url) else "",
                original_filename=original_filename,
                file_path=file_path_str,
                text_path=text_path_str,
                summary=summary,
            )

            return jsonify({
                "success": True,
                "report": {
                    "id": report_id,
                    "title": title,
                    "source_type": source_type,
                    "url": url,
                    "summary_preview": summary[:300],
                    "warning": warning,
                },
            })

        except Exception as e:
            logger.exception("수동 보고서 추가 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/focus/article/<article_id>", methods=["DELETE"])
    def focus_delete_article(article_id):
        article_id = (article_id or "").strip()
        if not article_id:
            return jsonify({"success": False, "error": "id가 필요합니다."}), 400
        try:
            ok = delete_manual_article(get_db(), article_id)
        except Exception as e:
            logger.exception("수동 기사 삭제 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500
        if not ok:
            return jsonify({"success": False, "error": "해당 id의 기사를 찾을 수 없습니다."}), 404
        return jsonify({"success": True, "deleted_id": article_id})

    @app.route("/focus/report/<report_id>", methods=["DELETE"])
    def focus_delete_report(report_id):
        report_id = (report_id or "").strip()
        if not report_id:
            return jsonify({"success": False, "error": "id가 필요합니다."}), 400
        try:
            row = delete_manual_report(get_db(), report_id)
        except Exception as e:
            logger.exception("수동 보고서 삭제 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500
        if row is None:
            return jsonify({"success": False, "error": "해당 id의 보고서를 찾을 수 없습니다."}), 404

        try:
            base = MANUAL_REPORTS_DIR.resolve()
            for key in ("file_path", "text_path"):
                val = (row.get(key) or "").strip()
                if not val:
                    continue
                p = Path(val).resolve()
                try:
                    p.relative_to(base)
                except ValueError:
                    logger.warning("보고서 부수 파일이 MANUAL_REPORTS_DIR 밖에 있음, 스킵: %s", p)
                    continue
                p.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("보고서 부수 파일 정리 일부 실패 (id=%s): %s", report_id, e)

        return jsonify({"success": True, "deleted_id": report_id})

    @app.errorhandler(413)
    def too_large(_e):
        return jsonify({
            "success": False,
            "error": "파일이 너무 큽니다 (50MB 한도).",
        }), 413

    @app.route("/focus/generate", methods=["POST"])
    def focus_generate():
        """Claude API로 Focus 보고서를 생성한다.

        PR3: ``reports`` 배열을 받아 선택된 보고서를 DB에서 조회 →
        Claude prompt에 ``<reports>`` 블록으로 주입.
        """
        data = request.get_json() or {}
        articles = data.get("articles", [])
        report_refs = data.get("reports", []) or []
        expert_insight = (data.get("expert_insight") or "").strip()

        if not articles and not report_refs:
            return jsonify({
                "success": False,
                "error": "선택된 기사 또는 보고서가 없습니다.",
            }), 400

        try:
            db = get_db()
            existing_summaries = get_existing_summaries(db)

            # 선택된 보고서 풀스펙 조회 + head_excerpt 보충 (text_path에서 첫 4000자)
            selected_reports: list[dict] = []
            for ref in report_refs:
                rid = ref.get("id") if isinstance(ref, dict) else None
                if not rid:
                    continue
                # 'report-{id}' prefix 처리
                if isinstance(rid, str) and rid.startswith("report-"):
                    rid = rid[len("report-"):]
                r = get_manual_report(db, rid)
                if r is None:
                    logger.warning("선택된 보고서를 찾을 수 없음 id=%s", rid)
                    continue
                # head_excerpt를 text_path에서 로드 (앞부분)
                excerpt = ""
                tp = r.get("text_path", "")
                if tp:
                    try:
                        excerpt = Path(tp).read_text(encoding="utf-8")[:4000]
                    except OSError as e:
                        logger.warning("보고서 전문 로드 실패 %s: %s", tp, e)
                selected_reports.append({**r, "head_excerpt": excerpt})

            claude_api_key = os.environ.get("CLAUDE_API_KEY", "")
            claude = ClaudeService(get_cfg(), claude_api_key)
            markdown = claude.generate_focus(
                articles, existing_summaries,
                reports=selected_reports or None,
                expert_insight=expert_insight,
            )

            date_display = get_kst_display_date()
            html_preview = render_email_html(markdown, "focus", date_display)

            return jsonify({
                "success": True,
                "markdown": markdown,
                "html_preview": html_preview,
            })
        except Exception as e:
            logger.error("주간 보고서 생성 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/focus/publish", methods=["POST"])
    def focus_publish():
        """Focus 보고서를 발간한다 (Gmail 발송 → 로컬 백업).

        2-2: ``edited_html``이 있으면 사용자가 미리보기에서 직접 편집한 HTML을
        그대로 이메일에 사용. 없으면 ``markdown``을 ``render_email_html``로
        변환 (기존 동작).
        """
        data = request.get_json() or {}
        markdown = data.get("markdown", "")
        edited_html = (data.get("edited_html") or "").strip()
        if not markdown:
            return jsonify({"success": False, "error": "마크다운 내용이 없습니다."}), 400

        cfg = get_cfg()
        db = get_db()
        date_str = get_kst_date_str()
        date_display = get_kst_display_date()
        creds_path = str(BASE_DIR / "credentials" / "google_credentials.json")
        token_path = str(BASE_DIR / "credentials" / "google_token.json")
        results = {"email": None, "backup": None, "git_sync": None}

        # P0(2026-05-13): publish 직전 git pull. 충돌 시 발송 차단.
        git_sync = GitSync(BASE_DIR, cfg)
        try:
            git_sync.pull_or_fail()
        except GitSyncError as e:
            logger.error("git_sync pull 실패 — Focus 발송 차단: %s", e)
            return jsonify({
                "success": False,
                "error": f"git_sync pull 실패 (수동 해결 필요): {e}",
            }), 409

        # ── Step 4: Gmail 발송 ──
        try:
            recipients = cfg.get("recipients", {}).get("focus", [])
            if edited_html:
                # 사용자가 미리보기 편집 → 그 HTML을 그대로 발송 (Drive 링크 갱신만 시도)
                html_body = edited_html
                logger.info("Focus 발송: 사용자 편집 HTML 사용 (%d자)", len(edited_html))
            else:
                html_body = render_email_html(markdown, "focus", date_display)
                logger.info("Focus 발송: markdown→HTML 렌더 사용")
            subject = build_email_subject("focus", date_str)

            creds = get_google_credentials(creds_path, token_path)
            gmail = GmailService(creds)
            gmail.send_email(recipients, subject, html_body)
            results["email"] = {"success": True, "recipients": len(recipients)}
            logger.info("Focus 이메일 발송 완료 (%d명)", len(recipients))
        except Exception as e:
            logger.error("Focus 이메일 발송 실패: %s", e)
            log_newsletter(db, "focus", 0, 0, "failed", error_message=str(e))
            return jsonify({
                "success": False,
                "error": f"이메일 발송 실패: {e}",
                "results": results,
            }), 500

        # 로컬 마크다운 백업
        try:
            backup_dir = BASE_DIR / "data" / "newsletters"
            backup_dir.mkdir(parents=True, exist_ok=True)
            filepath = backup_dir / f"focus_{date_str}.md"
            filepath.write_text(markdown, encoding="utf-8")
            results["backup"] = {"success": True, "path": str(filepath)}
            logger.info("Focus 로컬 백업 저장: %s", filepath)
        except Exception as e:
            logger.error("Focus 로컬 백업 실패 (계속 진행): %s", e)
            results["backup"] = {"success": False, "error": str(e)}

        # ── 발송 이력 기록 ──
        log_newsletter(db, "focus", 0, len(recipients), "success")

        # P0(2026-05-13): data/ 변경분 git commit + push. push 실패는 warn만.
        try:
            results["git_sync"] = git_sync.commit_and_push("focus", date_str)
        except Exception as e:
            logger.warning("git_sync commit/push 예외 (발송은 완료): %s", e)
            results["git_sync"] = {"committed": False, "pushed": False,
                                   "skipped": "exception", "error": str(e)}

        return jsonify({"success": True, "results": results})

    # ── 공통 ──

    @app.route("/reset-today", methods=["POST"])
    def reset_today():
        """오늘 날짜의 기사·아카이브·로컬 백업을 초기화한다 (수동 테스트용).

        발송 이력(newsletter_log)은 보존한다.
        """
        try:
            db = get_db()
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
            for pattern in [f"daily_{date_str}.md", f"weekly_{date_str}.md",
                            f"focus_{date_str}.md"]:
                filepath = backup_dir / pattern
                if filepath.exists():
                    filepath.unlink()
                    files_deleted.append(pattern)

            logger.info(
                "테스트 초기화 완료: 아카이브 %d건, daily %d건, manual %d건, 파일 %s",
                archive_deleted, daily_deleted, manual_deleted, files_deleted,
            )
            return jsonify({
                "success": True,
                "date": date_str,
                "archive_deleted": archive_deleted,
                "daily_deleted": daily_deleted,
                "manual_deleted": manual_deleted,
                "files_deleted": files_deleted,
            })
        except Exception as e:
            logger.error("테스트 초기화 실패: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

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
