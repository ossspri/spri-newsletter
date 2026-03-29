"""tests/test_db.py — SQLite DB 모듈 TDD 테스트"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.db import (
    init_db,
    insert_daily_articles,
    insert_manual_article,
    get_articles_for_date_range,
    get_existing_summaries,
    check_today_sent,
    log_newsletter,
    archive_articles,
    get_weekly_articles,
)


@pytest.fixture
def db(tmp_path):
    """인메모리 대신 tmp_path에 DB 생성하여 테스트."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    yield conn
    conn.close()


# ── 스키마 검증 ──

class TestSchema:
    def test_tables_exist(self, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert "daily_articles" in tables
        assert "manual_articles" in tables
        assert "article_archive" in tables
        assert "newsletter_log" in tables

    def test_daily_articles_columns(self, db):
        cursor = db.execute("PRAGMA table_info(daily_articles)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {"id", "collected_at", "title", "url", "description",
                    "source_name", "published_at", "used_in"}
        assert expected == cols

    def test_newsletter_log_columns(self, db):
        cursor = db.execute("PRAGMA table_info(newsletter_log)")
        cols = {row[1] for row in cursor.fetchall()}
        expected = {"id", "sent_at", "type", "article_count",
                    "recipient_count", "status", "error_message",
                    "drive_doc_id", "nlm_notebook"}
        assert expected == cols


# ── daily_articles CRUD ──

class TestDailyArticles:
    def _sample_articles(self):
        return [
            {
                "title": "AI Revolution in SW Industry",
                "url": "https://example.com/article1",
                "description": "AI is transforming...",
                "source_name": "TechNews",
                "published_at": "2026-03-29T01:00:00Z",
            },
            {
                "title": "GPU Market Surge",
                "url": "https://example.com/article2",
                "description": "GPU demand rises...",
                "source_name": "HardwareWeekly",
                "published_at": "2026-03-29T02:00:00Z",
            },
        ]

    def test_insert_and_query(self, db):
        articles = self._sample_articles()
        count = insert_daily_articles(db, articles)
        assert count == 2

        rows = db.execute("SELECT * FROM daily_articles").fetchall()
        assert len(rows) == 2

    def test_dedup_on_url(self, db):
        articles = self._sample_articles()
        insert_daily_articles(db, articles)
        # 같은 URL 재삽입 시 중복 무시
        count = insert_daily_articles(db, articles)
        assert count == 0

        rows = db.execute("SELECT * FROM daily_articles").fetchall()
        assert len(rows) == 2

    def test_partial_dedup(self, db):
        articles = self._sample_articles()
        insert_daily_articles(db, articles)

        new_articles = [
            articles[0],  # 중복
            {
                "title": "New Article",
                "url": "https://example.com/article3",
                "description": "Brand new",
                "source_name": "NewSource",
                "published_at": "2026-03-29T03:00:00Z",
            },
        ]
        count = insert_daily_articles(db, new_articles)
        assert count == 1

        rows = db.execute("SELECT * FROM daily_articles").fetchall()
        assert len(rows) == 3


# ── manual_articles ──

class TestManualArticles:
    def test_insert_manual(self, db):
        insert_manual_article(db, "Manual Title", "https://manual.com/1", "desc")
        rows = db.execute("SELECT * FROM manual_articles").fetchall()
        assert len(rows) == 1
        assert rows[0][2] == "Manual Title"  # title

    def test_dedup_manual(self, db):
        insert_manual_article(db, "Title", "https://manual.com/1", "desc")
        insert_manual_article(db, "Title", "https://manual.com/1", "desc")
        rows = db.execute("SELECT * FROM manual_articles").fetchall()
        assert len(rows) == 1


# ── get_articles_for_date_range ──

class TestDateRange:
    def test_filter_by_date(self, db):
        articles = [
            {
                "title": "Old Article",
                "url": "https://example.com/old",
                "description": "old",
                "source_name": "Src",
                "published_at": "2026-03-20T01:00:00Z",
            },
            {
                "title": "Recent Article",
                "url": "https://example.com/recent",
                "description": "recent",
                "source_name": "Src",
                "published_at": "2026-03-29T01:00:00Z",
            },
        ]
        insert_daily_articles(db, articles)

        results = get_articles_for_date_range(db, "2026-03-28", "2026-03-30")
        assert len(results) == 1
        assert results[0]["title"] == "Recent Article"


# ── existing summaries (중복 배제용) ──

class TestExistingSummaries:
    def test_empty_when_no_archive(self, db):
        summaries = get_existing_summaries(db)
        assert summaries == ""

    def test_returns_titles_from_archive(self, db):
        db.execute(
            "INSERT INTO article_archive (newsletter_date, newsletter_type, section, article_title, article_url) VALUES (?, ?, ?, ?, ?)",
            ("2026-03-28", "daily", "개요", "**AI 혁명이 SW 산업 변화를 가속화**", "https://example.com/1"),
        )
        db.execute(
            "INSERT INTO article_archive (newsletter_date, newsletter_type, section, article_title, article_url) VALUES (?, ?, ?, ?, ?)",
            ("2026-03-28", "daily", "기업/산업", "**빅테크 AI 투자 확대**", "https://example.com/2"),
        )
        db.commit()

        summaries = get_existing_summaries(db)
        assert "AI 혁명이 SW 산업 변화를 가속화" in summaries
        assert "빅테크 AI 투자 확대" in summaries


# ── check_today_sent ──

class TestCheckTodaySent:
    def test_false_when_no_log(self, db):
        assert check_today_sent(db, "daily") is False

    def test_true_when_sent_today(self, db):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "INSERT INTO newsletter_log (sent_at, type, article_count, recipient_count, status) VALUES (?, ?, ?, ?, ?)",
            (now, "daily", 10, 5, "success"),
        )
        db.commit()
        assert check_today_sent(db, "daily") is True

    def test_false_for_different_type(self, db):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "INSERT INTO newsletter_log (sent_at, type, article_count, recipient_count, status) VALUES (?, ?, ?, ?, ?)",
            (now, "weekly", 10, 5, "success"),
        )
        db.commit()
        assert check_today_sent(db, "daily") is False

    def test_false_for_failed_status(self, db):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        db.execute(
            "INSERT INTO newsletter_log (sent_at, type, article_count, recipient_count, status) VALUES (?, ?, ?, ?, ?)",
            (now, "daily", 10, 5, "failed"),
        )
        db.commit()
        assert check_today_sent(db, "daily") is False


# ── log_newsletter ──

class TestLogNewsletter:
    def test_log_success(self, db):
        log_newsletter(db, "daily", 15, 3, "success")
        rows = db.execute("SELECT * FROM newsletter_log").fetchall()
        assert len(rows) == 1
        assert rows[0][4] == 3  # recipient_count

    def test_log_with_optional_fields(self, db):
        log_newsletter(
            db, "weekly", 20, 5, "success",
            drive_doc_id="doc_123", nlm_notebook="SPRi_2026_0330",
        )
        row = db.execute("SELECT drive_doc_id, nlm_notebook FROM newsletter_log").fetchone()
        assert row[0] == "doc_123"
        assert row[1] == "SPRi_2026_0330"


# ── archive_articles ──

class TestArchiveArticles:
    def test_archive(self, db):
        articles_data = [
            {"section": "개요", "title": "AI News", "url": "https://example.com/1"},
            {"section": "기업/산업", "title": "Tech News", "url": "https://example.com/2"},
        ]
        archive_articles(db, "2026-03-29", "daily", articles_data)

        rows = db.execute("SELECT * FROM article_archive").fetchall()
        assert len(rows) == 2


# ── get_weekly_articles (7일간 기사) ──

class TestGetWeeklyArticles:
    def test_returns_7_days(self, db):
        today = datetime.now()
        for i in range(10):
            d = today - timedelta(days=i)
            db.execute(
                "INSERT INTO daily_articles (collected_at, title, url, description, source_name, published_at) VALUES (?, ?, ?, ?, ?, ?)",
                (d.strftime("%Y-%m-%dT%H:%M:%S"), f"Article {i}",
                 f"https://example.com/{i}", "desc", "Src",
                 d.strftime("%Y-%m-%dT%H:%M:%SZ")),
            )
        db.commit()

        results = get_weekly_articles(db)
        # 7일 timedelta 기준: 오늘 포함 최대 8건 (경계 시각에 따라 7~8)
        assert len(results) <= 8
        assert len(results) >= 7
