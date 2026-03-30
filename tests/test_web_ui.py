"""tests/test_web_ui.py — 웹 UI Flask 앱 테스트 (Phase 6)"""
import json
from unittest.mock import patch, MagicMock

import pytest

from src.db import insert_daily_articles, log_newsletter
from web_ui.app import create_app
from tests.conftest import create_fake_sheets_db


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
def db_conn():
    """인메모리 SheetsDB."""
    return create_fake_sheets_db()


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


class TestDailySend:
    """POST /daily/send 이메일 발송 테스트."""

    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.GmailService")
    def test_send_success(self, mock_gmail_cls, mock_auth, client):
        """이메일 발송 성공 시 결과를 반환한다."""
        mock_auth.return_value = MagicMock()
        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg123"}
        mock_gmail_cls.return_value = mock_gmail

        resp = client.post(
            "/daily/send",
            data=json.dumps({"markdown": SAMPLE_MARKDOWN}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True

    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.GmailService")
    def test_send_missing_markdown(self, mock_gmail_cls, mock_auth, client):
        """마크다운 없이 요청하면 에러를 반환한다."""
        resp = client.post(
            "/daily/send",
            data=json.dumps({}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 400
        assert data["success"] is False


class TestDailySaveDrive:
    """POST /daily/save-drive Google Drive 저장 테스트."""

    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.DriveService")
    def test_save_drive_success(self, mock_drive_cls, mock_auth, client):
        """Drive 저장 성공 시 문서 ID를 반환한다."""
        mock_auth.return_value = MagicMock()
        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_abc123"
        mock_drive_cls.return_value = mock_drive

        resp = client.post(
            "/daily/save-drive",
            data=json.dumps({"markdown": SAMPLE_MARKDOWN}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["doc_id"] == "doc_abc123"


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


class TestWeeklySend:
    """POST /weekly/send 이메일 발송 테스트."""

    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.GmailService")
    def test_send_weekly_success(self, mock_gmail_cls, mock_auth, client):
        """주간 이메일 발송 성공 시 결과를 반환한다."""
        mock_auth.return_value = MagicMock()
        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg456"}
        mock_gmail_cls.return_value = mock_gmail

        resp = client.post(
            "/weekly/send",
            data=json.dumps({"markdown": SAMPLE_MARKDOWN}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True


class TestWeeklySaveDrive:
    """POST /weekly/save-drive Google Drive 저장 테스트."""

    @patch("web_ui.app.get_google_credentials")
    @patch("web_ui.app.DriveService")
    def test_save_drive_weekly(self, mock_drive_cls, mock_auth, client):
        """Weekly Drive 저장 성공."""
        mock_auth.return_value = MagicMock()
        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_weekly_123"
        mock_drive_cls.return_value = mock_drive

        resp = client.post(
            "/weekly/save-drive",
            data=json.dumps({"markdown": SAMPLE_MARKDOWN}),
            content_type="application/json",
        )
        data = json.loads(resp.data)

        assert resp.status_code == 200
        assert data["success"] is True
        assert data["doc_id"] == "doc_weekly_123"


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
