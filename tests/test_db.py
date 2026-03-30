"""tests/test_db.py — Google Sheets DB 모듈 테스트"""
from datetime import datetime, timedelta

import pytest

from src.db import (
    insert_daily_articles,
    insert_manual_article,
    get_articles_for_date_range,
    get_existing_summaries,
    check_today_sent,
    log_newsletter,
    archive_articles,
    get_weekly_articles,
    get_daily_articles_today,
    get_all_manual_articles,
    SHEET_HEADERS,
)


# ── 스키마 검증 ──

class TestSchema:
    def test_sheets_exist(self, db):
        """4개 시트 탭이 존재한다."""
        titles = {ws.title for ws in db.spreadsheet.worksheets()}
        assert "daily_articles" in titles
        assert "manual_articles" in titles
        assert "article_archive" in titles
        assert "newsletter_log" in titles

    def test_daily_articles_headers(self, db):
        headers = db.worksheet("daily_articles").row_values(1)
        expected = SHEET_HEADERS["daily_articles"]
        assert headers == expected

    def test_newsletter_log_headers(self, db):
        headers = db.worksheet("newsletter_log").row_values(1)
        expected = SHEET_HEADERS["newsletter_log"]
        assert headers == expected


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

        records = db.worksheet("daily_articles").get_all_records()
        assert len(records) == 2

    def test_dedup_on_url(self, db):
        articles = self._sample_articles()
        insert_daily_articles(db, articles)
        # 같은 URL 재삽입 시 중복 무시
        count = insert_daily_articles(db, articles)
        assert count == 0

        records = db.worksheet("daily_articles").get_all_records()
        assert len(records) == 2

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

        records = db.worksheet("daily_articles").get_all_records()
        assert len(records) == 3


# ── manual_articles ──

class TestManualArticles:
    def test_insert_manual(self, db):
        insert_manual_article(db, "Manual Title", "https://manual.com/1", "desc")
        records = db.worksheet("manual_articles").get_all_records()
        assert len(records) == 1
        assert records[0]["title"] == "Manual Title"

    def test_dedup_manual(self, db):
        insert_manual_article(db, "Title", "https://manual.com/1", "desc")
        result = insert_manual_article(db, "Title", "https://manual.com/1", "desc")
        assert result is False
        records = db.worksheet("manual_articles").get_all_records()
        assert len(records) == 1


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
        ws = db.worksheet("article_archive")
        ws.append_row([1, "2026-03-28", "daily", "개요",
                        "**AI 혁명이 SW 산업 변화를 가속화**", "https://example.com/1", ""])
        ws.append_row([2, "2026-03-28", "daily", "기업/산업",
                        "**빅테크 AI 투자 확대**", "https://example.com/2", ""])

        summaries = get_existing_summaries(db)
        assert "AI 혁명이 SW 산업 변화를 가속화" in summaries
        assert "빅테크 AI 투자 확대" in summaries


# ── check_today_sent ──

class TestCheckTodaySent:
    def test_false_when_no_log(self, db):
        assert check_today_sent(db, "daily") is False

    def test_true_when_sent_today(self, db):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ws = db.worksheet("newsletter_log")
        ws.append_row([1, now, "daily", 10, 5, "success", "", "", ""])
        assert check_today_sent(db, "daily") is True

    def test_false_for_different_type(self, db):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ws = db.worksheet("newsletter_log")
        ws.append_row([1, now, "weekly", 10, 5, "success", "", "", ""])
        assert check_today_sent(db, "daily") is False

    def test_false_for_failed_status(self, db):
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        ws = db.worksheet("newsletter_log")
        ws.append_row([1, now, "daily", 10, 5, "failed", "", "", ""])
        assert check_today_sent(db, "daily") is False


# ── log_newsletter ──

class TestLogNewsletter:
    def test_log_success(self, db):
        log_newsletter(db, "daily", 15, 3, "success")
        records = db.worksheet("newsletter_log").get_all_records()
        assert len(records) == 1
        assert records[0]["recipient_count"] == 3

    def test_log_with_optional_fields(self, db):
        log_newsletter(
            db, "weekly", 20, 5, "success",
            drive_doc_id="doc_123", nlm_notebook="SPRi_2026_0330",
        )
        records = db.worksheet("newsletter_log").get_all_records()
        assert records[0]["drive_doc_id"] == "doc_123"
        assert records[0]["nlm_notebook"] == "SPRi_2026_0330"


# ── archive_articles ──

class TestArchiveArticles:
    def test_archive(self, db):
        articles_data = [
            {"section": "개요", "title": "AI News", "url": "https://example.com/1"},
            {"section": "기업/산업", "title": "Tech News", "url": "https://example.com/2"},
        ]
        archive_articles(db, "2026-03-29", "daily", articles_data)

        records = db.worksheet("article_archive").get_all_records()
        assert len(records) == 2


# ── get_weekly_articles (7일간 기사) ──

class TestGetWeeklyArticles:
    def test_returns_7_days(self, db):
        today = datetime.now()
        ws = db.worksheet("daily_articles")
        for i in range(10):
            d = today - timedelta(days=i)
            ws.append_row([
                i + 1, d.strftime("%Y-%m-%dT%H:%M:%S"),
                f"Article {i}", f"https://example.com/{i}",
                "desc", "Src", d.strftime("%Y-%m-%dT%H:%M:%SZ"), "",
            ])

        results = get_weekly_articles(db)
        # 7일 timedelta 기준: 오늘 포함 최대 8건 (경계 시각에 따라 7~8)
        assert len(results) <= 8
        assert len(results) >= 7


# ── get_daily_articles_today ──

class TestGetDailyArticlesToday:
    def test_returns_today_only(self, db):
        today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        ws = db.worksheet("daily_articles")
        ws.append_row([1, today, "Today Article", "https://example.com/today",
                        "desc", "Src", today, ""])
        ws.append_row([2, yesterday, "Yesterday Article", "https://example.com/yesterday",
                        "desc", "Src", yesterday, ""])

        results = get_daily_articles_today(db)
        assert len(results) == 1
        assert results[0]["title"] == "Today Article"


# ── get_all_manual_articles ──

class TestGetAllManualArticles:
    def test_returns_all_sorted(self, db):
        ws = db.worksheet("manual_articles")
        ws.append_row([1, "2026-03-28T10:00:00", "Older", "https://a.com/1", "d", "expert"])
        ws.append_row([2, "2026-03-29T10:00:00", "Newer", "https://a.com/2", "d", "expert"])

        results = get_all_manual_articles(db)
        assert len(results) == 2
        assert results[0]["title"] == "Newer"  # 최신순
