"""tests/test_main.py — 파이프라인 통합 테스트"""
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from main import (
    run_daily_pipeline,
    run_fetch_only,
    _fallback_articles_markdown,
    _save_local_backup,
    load_config,
)
from src.db import init_db


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
    "logging": {"level": "INFO", "file": "logs/spri.log"},
}

SAMPLE_ARTICLES = [
    {
        "title": "AI Revolution",
        "url": "https://example.com/1",
        "description": "AI is changing everything",
        "source_name": "TechNews",
        "published_at": "2026-03-29T10:00:00Z",
    },
    {
        "title": "GPU Market Boom",
        "url": "https://example.com/2",
        "description": "GPU demand surges",
        "source_name": "HardwareWeekly",
        "published_at": "2026-03-29T08:00:00Z",
    },
]

SAMPLE_MARKDOWN = """\
## 1. 개요

**AI가 SW 산업을 재편하고 있음**
글로벌 AI 기술이 소프트웨어 산업을 변화시키고 있음.
"""


@pytest.fixture
def db_conn():
    """인메모리 SQLite DB."""
    conn = init_db(":memory:")
    yield conn
    conn.close()


class TestDailyPipeline:
    """Daily 파이프라인 통합 테스트."""

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_success(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """정상 실행 시 모든 단계를 거친다."""
        # GNews mock
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        # Claude mock
        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        # Gmail mock
        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail

        # Auth mock
        mock_auth.return_value = MagicMock()

        # Drive mock
        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_abc123"
        mock_drive_cls.return_value = mock_drive

        # NotebookLM mock
        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_123"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        mock_gnews.fetch_articles.assert_called_once()
        mock_claude.generate_daily.assert_called_once()
        mock_gmail.send_email.assert_called_once()
        mock_drive.create_document.assert_called_once()
        mock_nlm.save_sources.assert_called_once()

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_logs_success(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """성공 시 newsletter_log에 success로 기록한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_abc"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_abc"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT status FROM newsletter_log ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        assert row[0] == "success"

    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key"})
    def test_daily_pipeline_gnews_failure(self, mock_gnews_cls, db_conn):
        """GNews 실패 시 failed로 기록하고 종료한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.side_effect = Exception("API limit exceeded")
        mock_gnews_cls.return_value = mock_gnews

        run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT status, error_message FROM newsletter_log")
        row = cursor.fetchone()
        assert row[0] == "failed"
        assert "GNews" in row[1]

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_claude_failure_fallback(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """Claude 실패 시 기사 목록만으로 이메일을 발송한다 (PRD 10)."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.side_effect = Exception("Claude API timeout")
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_fallback"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_fallback"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_fallback"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        # Gmail은 여전히 호출됨
        mock_gmail.send_email.assert_called_once()

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_gmail_failure(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """Gmail 실패 시 failed로 기록하고 Drive/NLM은 건너뛴다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.side_effect = Exception("Gmail auth failed")
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT status FROM newsletter_log ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        assert row[0] == "failed"

        # Gmail 실패 시 Drive/NLM은 호출되지 않음
        mock_drive.create_document.assert_not_called()
        mock_nlm.save_sources.assert_not_called()

    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_zero_articles(
        self, mock_gnews_cls, mock_gmail_cls, mock_auth, db_conn
    ):
        """기사 0건이면 대체 메시지를 발송한다 (PRD 10)."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = []
        mock_gnews_cls.return_value = mock_gnews

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_empty"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        with patch("main._save_local_backup"), \
             patch("main.DriveService") as mock_drive_cls, \
             patch("main.NotebookLMService") as mock_nlm_cls:
            mock_drive = MagicMock()
            mock_drive.create_document.return_value = "doc_empty"
            mock_drive_cls.return_value = mock_drive

            mock_nlm = MagicMock()
            mock_nlm_cls.return_value = mock_nlm

            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        # Gmail 호출됨 (대체 메시지)
        mock_gmail.send_email.assert_called_once()
        call_args = mock_gmail.send_email.call_args
        html_body = call_args[0][2]
        assert "해당 기간" in html_body or "동향 없음" in html_body

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_archives_articles(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """발송 후 기사를 아카이브에 저장한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_arch"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_arch"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT COUNT(*) FROM article_archive")
        assert cursor.fetchone()[0] == 2

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_inserts_articles_to_db(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """수집된 기사를 daily_articles 테이블에 삽입한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_ins"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_ins"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT COUNT(*) FROM daily_articles")
        assert cursor.fetchone()[0] == 2

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_daily_pipeline_correct_recipients(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """config의 daily 수신자에게 발송한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_recip"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_recip"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        call_args = mock_gmail.send_email.call_args
        recipients = call_args[0][0]
        assert recipients == ["analyst1@spri.kr", "analyst2@spri.kr"]


class TestFetchOnly:
    """fetch-only 모드 테스트."""

    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key"})
    def test_fetch_only_collects_articles(self, mock_gnews_cls, db_conn):
        """기사를 수집하고 DB에 저장한다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        run_fetch_only(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT COUNT(*) FROM daily_articles")
        assert cursor.fetchone()[0] == 2

    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key"})
    def test_fetch_only_gnews_failure(self, mock_gnews_cls, db_conn):
        """GNews 실패 시 에러를 로깅하고 종료한다 (예외 미전파)."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.side_effect = Exception("Network error")
        mock_gnews_cls.return_value = mock_gnews

        # 예외가 전파되지 않아야 함
        run_fetch_only(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute("SELECT COUNT(*) FROM daily_articles")
        assert cursor.fetchone()[0] == 0

    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key"})
    def test_fetch_only_no_gmail_call(self, mock_gnews_cls, db_conn):
        """fetch-only는 이메일을 발송하지 않는다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        with patch("main.GmailService") as mock_gmail_cls:
            run_fetch_only(SAMPLE_CONFIG, db_conn)
            mock_gmail_cls.assert_not_called()


class TestFallbackArticlesMarkdown:
    """Claude 실패 시 fallback 마크다운 생성 테스트."""

    def test_fallback_contains_titles(self):
        md = _fallback_articles_markdown(SAMPLE_ARTICLES)
        assert "AI Revolution" in md
        assert "GPU Market Boom" in md

    def test_fallback_contains_urls(self):
        md = _fallback_articles_markdown(SAMPLE_ARTICLES)
        assert "https://example.com/1" in md
        assert "https://example.com/2" in md

    def test_fallback_has_header(self):
        md = _fallback_articles_markdown(SAMPLE_ARTICLES)
        assert "## 수집된 기사 목록" in md

    def test_fallback_empty_articles(self):
        md = _fallback_articles_markdown([])
        assert "## 수집된 기사 목록" in md


class TestSaveLocalBackup:
    """로컬 백업 저장 테스트."""

    def test_saves_markdown_file(self, tmp_path):
        """마크다운 파일이 저장된다."""
        with patch("main.BASE_DIR", tmp_path):
            _save_local_backup(SAMPLE_MARKDOWN, "daily", "2026-03-29")

        filepath = tmp_path / "data" / "newsletters" / "daily_2026-03-29.md"
        assert filepath.exists()
        assert filepath.read_text(encoding="utf-8") == SAMPLE_MARKDOWN

    def test_creates_directory_if_missing(self, tmp_path):
        """디렉토리가 없으면 생성한다."""
        with patch("main.BASE_DIR", tmp_path):
            _save_local_backup("test", "weekly", "2026-03-29")

        assert (tmp_path / "data" / "newsletters").is_dir()

    def test_weekly_filename(self, tmp_path):
        """weekly 타입은 weekly_ 접두사를 사용한다."""
        with patch("main.BASE_DIR", tmp_path):
            _save_local_backup("test", "weekly", "2026-03-29")

        filepath = tmp_path / "data" / "newsletters" / "weekly_2026-03-29.md"
        assert filepath.exists()


class TestDriveIntegration:
    """Daily 파이프라인 — Drive 연동 테스트 (Phase 5)."""

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_drive_doc_id_saved_to_log(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """Drive 문서 ID가 newsletter_log에 기록된다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_phase5"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_phase5"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute(
            "SELECT drive_doc_id FROM newsletter_log ORDER BY id DESC LIMIT 1"
        )
        assert cursor.fetchone()[0] == "doc_phase5"

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_drive_failure_does_not_break_pipeline(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """Drive 저장 실패 시에도 파이프라인은 계속 진행한다 (PRD 10)."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        # Drive 실패
        mock_drive = MagicMock()
        mock_drive.create_document.side_effect = Exception("Drive quota exceeded")
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_ok"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        # 파이프라인 완료 — 로그에 success, drive_doc_id는 NULL
        cursor = db_conn.execute(
            "SELECT status, drive_doc_id FROM newsletter_log ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        assert row[0] == "success"
        assert row[1] is None

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_drive_skipped_when_gmail_failed(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """Gmail 실패 시 Drive는 호출되지 않는다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.side_effect = Exception("Gmail error")
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        mock_drive_cls.assert_not_called()

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_drive_receives_correct_params(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """Drive에 올바른 매개변수가 전달된다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_params"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_params"
        mock_nlm_cls.return_value = mock_nlm

        config_with_drive = {**SAMPLE_CONFIG, "drive": {"folder_id": "my_folder"}}

        with patch("main._save_local_backup"):
            run_daily_pipeline(config_with_drive, db_conn)

        call_kwargs = mock_drive.create_document.call_args
        assert call_kwargs[0][0] == SAMPLE_MARKDOWN  # markdown_body
        assert call_kwargs[0][1] == "daily"  # newsletter_type
        assert call_kwargs[0][3] == "my_folder"  # folder_id


class TestNotebookLMIntegration:
    """Daily 파이프라인 — NotebookLM 연동 테스트 (Phase 5)."""

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_nlm_notebook_saved_to_log(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """NotebookLM 노트북 ID가 newsletter_log에 기록된다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_nlm"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_phase5_nlm"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute(
            "SELECT nlm_notebook FROM newsletter_log ORDER BY id DESC LIMIT 1"
        )
        assert cursor.fetchone()[0] == "nb_phase5_nlm"

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_nlm_failure_does_not_break_pipeline(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """NotebookLM 저장 실패 시에도 파이프라인은 계속 진행한다 (PRD 10)."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_ok"
        mock_drive_cls.return_value = mock_drive

        # NLM 실패
        mock_nlm = MagicMock()
        mock_nlm.save_sources.side_effect = Exception("NLM auth expired")
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute(
            "SELECT status, nlm_notebook FROM newsletter_log ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
        assert row[0] == "success"
        assert row[1] is None

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_nlm_skipped_when_zero_articles(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """기사 0건이면 NotebookLM은 호출되지 않는다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = []
        mock_gnews_cls.return_value = mock_gnews

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_empty"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_zero"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        mock_nlm.save_sources.assert_not_called()

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_nlm_receives_articles_and_markdown(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """NotebookLM에 기사 목록과 마크다운이 전달된다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_art"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_art"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        call_args = mock_nlm.save_sources.call_args
        articles_arg = call_args[0][1]
        markdown_arg = call_args[0][2]

        assert len(articles_arg) == 2
        assert articles_arg[0]["title"] == "AI Revolution"
        assert articles_arg[0]["url"] == "https://example.com/1"
        assert markdown_arg == SAMPLE_MARKDOWN

    @patch("main.NotebookLMService")
    @patch("main.DriveService")
    @patch("main.get_google_credentials")
    @patch("main.GmailService")
    @patch("main.ClaudeService")
    @patch("main.GNewsService")
    @patch.dict("os.environ", {"GNEWS_API_KEY": "test_key", "CLAUDE_API_KEY": "test_claude"})
    def test_nlm_notebook_id_in_archive(
        self, mock_gnews_cls, mock_claude_cls, mock_gmail_cls, mock_auth,
        mock_drive_cls, mock_nlm_cls, db_conn
    ):
        """아카이브에 nlm_notebook_id가 기록된다."""
        mock_gnews = MagicMock()
        mock_gnews.fetch_articles.return_value = SAMPLE_ARTICLES
        mock_gnews_cls.return_value = mock_gnews

        mock_claude = MagicMock()
        mock_claude.generate_daily.return_value = SAMPLE_MARKDOWN
        mock_claude_cls.return_value = mock_claude

        mock_gmail = MagicMock()
        mock_gmail.send_email.return_value = {"id": "msg_123"}
        mock_gmail_cls.return_value = mock_gmail
        mock_auth.return_value = MagicMock()

        mock_drive = MagicMock()
        mock_drive.create_document.return_value = "doc_archive"
        mock_drive_cls.return_value = mock_drive

        mock_nlm = MagicMock()
        mock_nlm.save_sources.return_value = "nb_archive_id"
        mock_nlm_cls.return_value = mock_nlm

        with patch("main._save_local_backup"):
            run_daily_pipeline(SAMPLE_CONFIG, db_conn)

        cursor = db_conn.execute(
            "SELECT nlm_notebook_id FROM article_archive LIMIT 1"
        )
        assert cursor.fetchone()[0] == "nb_archive_id"
