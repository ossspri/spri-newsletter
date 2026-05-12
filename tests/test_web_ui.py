"""tests/test_web_ui.py — 웹 UI Flask 앱 테스트 (Phase 6)"""
import io
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.db import FileDB, insert_daily_articles, log_newsletter
from web_ui.app import create_app


SAMPLE_CONFIG = {
    "gnews": {
        "queries": ["software industry AI"],
        "lang": "en",
        "max_per_query": 10,
    },
    "newsletter": {
        "max_articles": 25,
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
    },
    "recipients": {
        "daily": ["analyst1@spri.kr", "analyst2@spri.kr"],
        "weekly": ["director@spri.kr"],
    },
    "drive": {"folder_id": "FAKE_FOLDER_ID"},
    "notebooklm": {"notebook_prefix": "SPRi"},
    "web_ui": {"host": "127.0.0.1", "port": 5000},
    "logging": {"level": "INFO", "file": "logs/spri.log"},
}

SAMPLE_ARTICLES = [
    {
        "title": "AI Revolution in Software",
        "url": "https://example.com/1",
        "description": "AI is changing everything",
        "source_name": "TechNews",
        "published_at": "2026-03-29T10:00:00Z",
    },
    {
        "title": "GPU Market Surge",
        "url": "https://example.com/2",
        "description": "GPU demand increases",
        "source_name": "HardwareWeekly",
        "published_at": "2026-03-29T08:00:00Z",
    },
]

SAMPLE_MARKDOWN = """\
## 1. 개요

**AI가 SW 산업을 재편하고 있음**
글로벌 AI 기술이 소프트웨어 산업을 변화시키고 있음.

* [AI Revolution in Software](https://example.com/1)
"""


@pytest.fixture
def db_conn(tmp_path):
    """임시 디렉토리 기반 FileDB."""
    return FileDB(tmp_path / "db")


@pytest.fixture
def app(db_conn):
    """Flask 테스트 앱."""
    application = create_app(SAMPLE_CONFIG, db_conn)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    """Flask 테스트 클라이언트."""
    return app.test_client()


# ── Daily 탭 ──


class TestDailyPage:
    """GET /daily 페이지 테스트."""

    def test_daily_page_loads(self, client):
        """Daily 페이지가 200 OK로 응답한다."""
        resp = client.get("/daily")
        assert resp.status_code == 200

    def test_daily_page_contains_tab(self, client):
        """Daily 페이지에 탭 네비게이션이 있다."""
        resp = client.get("/daily")
        html = resp.data.decode("utf-8")
        assert "Daily" in html
        assert "Weekly" in html

    def test_daily_page_shows_sent_badge(self, client, db_conn):
        """오늘 발송된 Daily가 있으면 배지를 표시한다."""
        log_newsletter(db_conn, "daily", 5, 2, "success")
        resp = client.get("/daily")
        html = resp.data.decode("utf-8")
        assert "발송 완료" in html

    def test_daily_page_shows_articles(self, client, db_conn):
        """수집된 기사 목록을 표시한다."""
        insert_daily_articles(db_conn, SAMPLE_ARTICLES)
        resp = client.get("/daily")
        html = resp.data.decode("utf-8")
        assert "AI Revolution" in html


class TestDailyFetch:
    """POST /daily/fetch 뉴스 수집 테스트."""

    @patch("web_ui.app.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key"})
    def test_fetch_success(self, mock_gnews_cls, client):
        """뉴스 수집 성공 시 결과를 반환한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        resp = client.post("/daily/fetch")
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["count"] == 2

    @patch("web_ui.app.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key"})
    def test_fetch_failure(self, mock_gnews_cls, client):
        """뉴스 수집 실패 시 에러를 반환한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.side_effect = Exception("API error")
        mock_gnews_cls.return_value = mock_gnews

        resp = client.post("/daily/fetch")
        data = json.loads(resp.data)

        assert resp.status_code == 500
        assert data["success"] is False
        assert "error" in data


class TestDailyGenerate:
    """POST /daily/generate 뉴스레터 생성 테스트."""

    @patch("web_ui.app.ClaudeService")
    @patch.dict("os.environ", {"CLAUDE_API_KEY": "test_key"})
    def test_generate_success(self, mock_claude_cls, client, db_conn):
        """뉴스레터 생성 성공 시 마크다운과 HTML을 반환한다."""
        insert_daily_articles(db_conn, SAMPLE_ARTICLES)

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        resp = client.post("/daily/generate")
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert "markdown" in data
        assert "html_preview" in data

    @patch("web_ui.app.ClaudeService")
    @patch.dict("os.environ", {"CLAUDE_API_KEY": "test_key"})
    def test_generate_failure(self, mock_claude_cls, client, db_conn):
        """Claude 실패 시 에러를 반환한다."""
        insert_daily_articles(db_conn, SAMPLE_ARTICLES)

        mock_claude = MagicMock()
        mock_claude.generate_daily.side_effect = Exception("Claude error")
        mock_claude_cls.return_value = mock_claude

        resp = client.post("/daily/generate")
        data = json.loads(resp.data)

        assert resp.status_code == 500
        assert data["success"] is False


class TestDailyPublish:
    """POST /daily/publish 뉴스레터 발간 테스트 (이메일 + Drive + NotebookLM)."""

    @patch("web_ui.app.NotebookLMService")
    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.DriveService")
    @patch("web_ui.app.GmailService")
    def test_publish_success(self, mock_gmail_cls, mock_drive_cls, mock_auth, mock_nlm_cls, client):
        """발간 성공 시 3단계 결과를 모두 반환한다."""
        mock_auth.return_value = MagicMock()
        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_abc123"
        mock_drive_cls.return_value = mock_drive
        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_xyz"
        mock_nlm_cls.return_value = mock_nlm

        resp = client.post(
            "/daily/publish",
            data=json.dumps({"markdown": SAMPLE_MARKDOWN}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["results"]["email"]["success"] is True
        assert data["results"]["drive"]["success"] is True

    def test_publish_missing_markdown(self, client):
        """마크다운 없이 요청하면 에러를 반환한다."""
        resp = client.post(
            "/daily/publish",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 400
        assert data["success"] is False


# ── Weekly 탭 ──


class TestWeeklyPage:
    """GET /weekly 페이지 테스트."""

    def test_weekly_page_loads(self, client):
        """Weekly 페이지가 200 OK로 응답한다."""
        resp = client.get("/weekly")
        assert resp.status_code == 200

    def test_weekly_page_shows_articles(self, client, db_conn):
        """주간 기사 목록을 표시한다."""
        insert_daily_articles(db_conn, SAMPLE_ARTICLES)
        resp = client.get("/weekly")
        html = resp.data.decode("utf-8")
        assert "AI Revolution" in html


class TestWeeklyAddArticle:
    """POST /weekly/add-article 수동 기사 추가 테스트."""

    @patch("web_ui.app.extract_url_metadata")
    def test_add_article_success(self, mock_extract, client):
        """URL로 기사를 추가할 수 있다."""
        mock_extract.return_value = {
            "title": "Manual Article",
            "description": "Manually added",
        }

        resp = client.post(
            "/weekly/add-article",
            data=json.dumps({"url": "https://example.com/manual"}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True

    def test_add_article_missing_url(self, client):
        """URL 없이 요청하면 에러를 반환한다."""
        resp = client.post(
            "/weekly/add-article",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 400
        assert data["success"] is False


class TestWeeklyGenerate:
    """POST /weekly/generate 주간 보고서 생성 테스트."""

    @patch("web_ui.app.ClaudeService")
    @patch.dict("os.environ", {"CLAUDE_API_KEY": "test_key"})
    def test_generate_weekly_success(self, mock_claude_cls, client):
        """주간 보고서 생성 성공 시 결과를 반환한다."""
        mock_claude = MagicMock()
        mock_claude.generate_weekly.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        resp = client.post(
            "/weekly/generate",
            data=json.dumps({
                "article_ids": [1, 2],
                "articles": SAMPLE_ARTICLES,
            }),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert "markdown" in data
        assert "html_preview" in data

    def test_generate_weekly_no_articles(self, client):
        """기사 없이 요청하면 에러를 반환한다."""
        resp = client.post(
            "/weekly/generate",
            data=json.dumps({"article_ids": [], "articles": []}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 400
        assert data["success"] is False


class TestWeeklyPublish:
    """POST /weekly/publish 보고서 발간 테스트 (이메일 + Drive + NotebookLM + 로컬 백업)."""

    @patch("pathlib.Path.write_text")
    @patch("pathlib.Path.mkdir")
    @patch("web_ui.app.NotebookLMService")
    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.DriveService")
    @patch("web_ui.app.GmailService")
    def test_publish_weekly_success(self, mock_gmail_cls, mock_drive_cls, mock_auth, mock_nlm_cls, mock_mkdir, mock_write, client):
        """발간 성공 시 전체 결과를 반환한다."""
        mock_auth.return_value = MagicMock()
        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg456"}
        mock_gmail_cls.return_value = mock_gmail
        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_weekly_123"
        mock_drive_cls.return_value = mock_drive
        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_weekly_xyz"
        mock_nlm_cls.return_value = mock_nlm

        resp = client.post(
            "/weekly/publish",
            data=json.dumps({"markdown": SAMPLE_MARKDOWN}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["results"]["email"]["success"] is True
        assert data["results"]["drive"]["success"] is True

    def test_publish_weekly_missing_markdown(self, client):
        """마크다운 없이 요청하면 에러를 반환한다."""
        resp = client.post(
            "/weekly/publish",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 400
        assert data["success"] is False


# ── 공통 기능 ──


class TestRootRedirect:
    """루트 경로 리다이렉트 테스트."""

    def test_root_redirects_to_daily(self, client):
        """/ 접근 시 /daily로 리다이렉트한다."""
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/daily" in resp.headers["Location"]


class TestPreviewEndpoint:
    """POST /preview 미리보기 테스트."""

    def test_preview_renders_html(self, client):
        """마크다운을 HTML 미리보기로 변환한다."""
        resp = client.post(
            "/preview",
            data=json.dumps({
                "markdown": SAMPLE_MARKDOWN,
                "type": "daily",
            }),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert "<h2" in data["html"]


# ── 수동 보고서 추가 (PR2) ──


class TestWeeklyAddReport:
    """POST /weekly/add-report — URL 또는 PDF 첨부."""

    def test_missing_both_inputs_returns_400(self, client):
        resp = client.post(
            "/weekly/add-report",
            data={},
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)
        assert resp.status_code == 400
        assert data["success"] is False

    @patch("web_ui.app.is_safe_url", return_value=False)
    def test_unsafe_url_returns_400(self, mock_safe, client):
        resp = client.post(
            "/weekly/add-report",
            data={"url": "http://127.0.0.1/admin"},
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)
        assert resp.status_code == 400
        assert "안전하지 않은" in data["error"] or "URL" in data["error"]

    @patch("web_ui.app.is_safe_url", return_value=True)
    @patch("web_ui.app.detect_url_kind", return_value="html")
    @patch("web_ui.app.extract_url_metadata")
    @patch("web_ui.app.insert_manual_report")
    @patch("web_ui.app.save_report_text", return_value=Path("data/manual_reports/x.txt"))
    def test_html_url_extracts_metadata_and_inserts(
        self, mock_save, mock_insert, mock_meta, mock_kind, mock_safe, client
    ):
        mock_meta.return_value = {
            "title": "IBM AI Index 2026 Overview",
            "description": "76% of enterprises have appointed CAIO...",
        }

        resp = client.post(
            "/weekly/add-report",
            data={"url": "https://example.com/ibm-ai-index"},
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["report"]["title"] == "IBM AI Index 2026 Overview"
        assert data["report"]["source_type"] == "url"
        # insert_manual_report 호출 검증
        mock_insert.assert_called_once()
        kwargs = mock_insert.call_args.kwargs
        assert kwargs["source_type"] == "url"
        assert kwargs["url"] == "https://example.com/ibm-ai-index"

    @patch("web_ui.app.is_safe_url", return_value=True)
    @patch("web_ui.app.detect_url_kind", return_value="pdf")
    @patch("web_ui.app.download_pdf")
    @patch("web_ui.app.extract_pdf_text", return_value=("full text body", "first 3 pages"))
    @patch("web_ui.app.ClaudeService")
    @patch("web_ui.app.insert_manual_report")
    @patch("web_ui.app.save_report_text", return_value=Path("data/manual_reports/x.txt"))
    @patch.dict("os.environ", {"CLAUDE_API_KEY": "sk-test"})
    def test_pdf_url_downloads_extracts_summarizes(
        self, mock_save, mock_insert, mock_claude_cls, mock_extract,
        mock_download, mock_kind, mock_safe, client
    ):
        mock_claude = MagicMock()
        mock_claude.summarize_report_text.return_value = "76% CAIO 신설..."
        mock_claude_cls.return_value = mock_claude

        resp = client.post(
            "/weekly/add-report",
            data={"url": "https://example.com/report.pdf"},
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["report"]["source_type"] == "pdf"
        mock_download.assert_called_once()
        mock_extract.assert_called_once()
        mock_claude.summarize_report_text.assert_called_once_with("full text body")

    @patch("web_ui.app.extract_pdf_text", return_value=("full text", "head excerpt"))
    @patch("web_ui.app.ClaudeService")
    @patch("web_ui.app.insert_manual_report")
    @patch("web_ui.app.save_report_text", return_value=Path("data/manual_reports/y.txt"))
    @patch.dict("os.environ", {"CLAUDE_API_KEY": "sk-test"})
    def test_pdf_file_upload(
        self, mock_save, mock_insert, mock_claude_cls, mock_extract, client, tmp_path
    ):
        mock_claude = MagicMock()
        mock_claude.summarize_report_text.return_value = "요약"
        mock_claude_cls.return_value = mock_claude

        # 유효한 PDF magic byte로 시작하는 더미 데이터
        pdf_bytes = b"%PDF-1.4\n" + b"x" * 1024
        with patch("web_ui.app.MANUAL_REPORTS_DIR", tmp_path):
            resp = client.post(
                "/weekly/add-report",
                data={
                    "file": (io.BytesIO(pdf_bytes), "ibm_ai_index_2026.pdf"),
                },
                content_type="multipart/form-data",
            )
            data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["report"]["source_type"] == "pdf"
        # 업로드된 파일이 tmp_path에 저장됐는지 확인
        saved = list(tmp_path.glob("*.pdf"))
        assert len(saved) == 1
        assert saved[0].read_bytes().startswith(b"%PDF-")

    def test_non_pdf_upload_rejected(self, client):
        resp = client.post(
            "/weekly/add-report",
            data={
                "file": (io.BytesIO(b"not a pdf"), "fake.pdf"),
            },
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)
        assert resp.status_code == 400
        assert "PDF" in data["error"]

    def test_wrong_extension_rejected(self, client):
        resp = client.post(
            "/weekly/add-report",
            data={
                "file": (io.BytesIO(b"%PDF-anything"), "evil.exe"),
            },
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)
        assert resp.status_code == 400
        assert "PDF" in data["error"]
