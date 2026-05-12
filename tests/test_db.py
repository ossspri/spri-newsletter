"""tests/test_db.py — 로컬 CSV DB 모듈 테스트"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.db import (
    SHEET_HEADERS,
    archive_articles,
    check_today_sent,
    clear_all_manual_reports,
    get_all_manual_articles,
    get_all_manual_reports,
    get_articles_for_date_range,
    get_daily_articles_today,
    get_existing_summaries,
    get_manual_report,
    get_weekly_articles,
    insert_daily_articles,
    insert_manual_article,
    insert_manual_report,
    log_newsletter,
)


# ── 스키마 검증 ──

class TestSchema:
    def test_tables_exist(self, db):
        """4개 CSV 테이블이 존재한다."""
        for name in SHEET_HEADERS:
            assert db.table(name).path.exists()

    def test_daily_articles_headers(self, db):
        assert db.table("daily_articles").headers == SHEET_HEADERS["daily_articles"]

    def test_newsletter_log_headers(self, db):
        assert db.table("newsletter_log").headers == SHEET_HEADERS["newsletter_log"]


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

        records = db.table("daily_articles").rows()
        assert len(records) == 2

    def test_dedup_on_url(self, db):
        articles = self._sample_articles()
        insert_daily_articles(db, articles)
        # 같은 URL 재삽입 시 중복 무시
        count = insert_daily_articles(db, articles)
        assert count == 0

        records = db.table("daily_articles").rows()
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

        records = db.table("daily_articles").rows()
        assert len(records) == 3


# ── manual_articles ──

class TestManualArticles:
    def test_insert_manual(self, db):
        insert_manual_article(db, "Manual Title", "https://manual.com/1", "desc")
        records = db.table("manual_articles").rows()
        assert len(records) == 1
        assert records[0]["title"] == "Manual Title"

    def test_dedup_manual(self, db):
        insert_manual_article(db, "Title", "https://manual.com/1", "desc")
        result = insert_manual_article(db, "Title", "https://manual.com/1", "desc")
        assert result is False
        records = db.table("manual_articles").rows()
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
        assert get_existing_summaries(db) == ""

    def test_returns_titles_from_archive(self, db):
        archive_articles(
            db, "2026-03-28", "daily",
            [
                {"section": "개요",
                 "title": "**AI 혁명이 SW 산업 변화를 가속화**",
                 "url": "https://example.com/1"},
                {"section": "기업/산업",
                 "title": "**빅테크 AI 투자 확대**",
                 "url": "https://example.com/2"},
            ],
        )

        summaries = get_existing_summaries(db)
        assert "AI 혁명이 SW 산업 변화를 가속화" in summaries
        assert "빅테크 AI 투자 확대" in summaries


# ── check_today_sent ──

class TestCheckTodaySent:
    def test_false_when_no_log(self, db):
        assert check_today_sent(db, "daily") is False

    def test_true_when_sent_today(self, db):
        log_newsletter(db, "daily", 10, 5, "success")
        assert check_today_sent(db, "daily") is True

    def test_false_for_different_type(self, db):
        log_newsletter(db, "weekly", 10, 5, "success")
        assert check_today_sent(db, "daily") is False

    def test_false_for_failed_status(self, db):
        log_newsletter(db, "daily", 10, 5, "failed")
        assert check_today_sent(db, "daily") is False


# ── check_today_sent: Gmail 위임 (PR#2) ──

class TestCheckTodaySentGmail:
    """``db.attach_gmail`` 주입 시 Gmail Sent 검색을 진실의 원천으로 사용한다."""

    def test_gmail_true_returns_true_even_if_csv_empty(self, db):
        """Gmail이 발송됨 → True (로컬 CSV가 비어있어도)."""
        gmail = MagicMock()
        gmail.search_sent_today.return_value = True
        db.attach_gmail(gmail)

        assert check_today_sent(db, "daily") is True
        gmail.search_sent_today.assert_called_once()

    def test_gmail_false_returns_false_even_if_csv_says_sent(self, db):
        """Gmail이 미발송 → False (CSV가 success로 잘못 갖고 있어도 Gmail 신뢰)."""
        gmail = MagicMock()
        gmail.search_sent_today.return_value = False
        db.attach_gmail(gmail)
        log_newsletter(db, "daily", 10, 5, "success")  # CSV에는 발송 기록 있음

        assert check_today_sent(db, "daily") is False

    def test_gmail_failure_falls_back_to_csv(self, db):
        """Gmail 호출 실패 → CSV fallback."""
        gmail = MagicMock()
        gmail.search_sent_today.side_effect = Exception("Gmail down")
        db.attach_gmail(gmail)
        log_newsletter(db, "daily", 10, 5, "success")

        assert check_today_sent(db, "daily") is True  # CSV 기준

    def test_no_gmail_uses_csv(self, db):
        """GmailService 미주입 시 CSV 그대로 사용."""
        log_newsletter(db, "daily", 10, 5, "success")
        assert check_today_sent(db, "daily") is True

    def test_gmail_called_with_today_kst_date(self, db):
        """Gmail 검색 호출 인자: type + 오늘(KST) YYYY-MM-DD."""
        gmail = MagicMock()
        gmail.search_sent_today.return_value = False
        db.attach_gmail(gmail)

        check_today_sent(db, "weekly")

        args = gmail.search_sent_today.call_args.args
        assert args[0] == "weekly"
        # YYYY-MM-DD 형식
        assert len(args[1]) == 10 and args[1][4] == "-" and args[1][7] == "-"


# ── log_newsletter ──

class TestLogNewsletter:
    def test_log_success(self, db):
        log_newsletter(db, "daily", 15, 3, "success")
        records = db.table("newsletter_log").rows()
        assert len(records) == 1
        assert records[0]["recipient_count"] == 3

    def test_log_with_optional_fields(self, db):
        log_newsletter(
            db, "weekly", 20, 5, "success",
            drive_doc_id="doc_123", nlm_notebook="SPRi_2026_0330",
        )
        records = db.table("newsletter_log").rows()
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

        records = db.table("article_archive").rows()
        assert len(records) == 2


# ── get_weekly_articles ──

class TestGetWeeklyArticles:
    def test_returns_7_days(self, db):
        today = datetime.now()
        for i in range(10):
            d = today - timedelta(days=i)
            db.table("daily_articles").append({
                "id": str(i + 1),
                "collected_at": d.strftime("%Y-%m-%dT%H:%M:%S"),
                "title": f"Article {i}",
                "url": f"https://example.com/{i}",
                "description": "desc",
                "source_name": "Src",
                "published_at": d.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "used_in": "",
            })

        results = get_weekly_articles(db)
        # 7일 timedelta 기준: 오늘 포함 최대 8건 (경계 시각에 따라 7~8)
        assert 7 <= len(results) <= 8


# ── get_daily_articles_today ──

class TestGetDailyArticlesToday:
    def test_returns_today_only(self, db):
        today = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        for collected, title, url in [
            (today, "Today Article", "https://example.com/today"),
            (yesterday, "Yesterday Article", "https://example.com/yesterday"),
        ]:
            db.table("daily_articles").append({
                "id": "1",
                "collected_at": collected,
                "title": title,
                "url": url,
                "description": "desc",
                "source_name": "Src",
                "published_at": collected,
                "used_in": "",
            })

        results = get_daily_articles_today(db)
        assert len(results) == 1
        assert results[0]["title"] == "Today Article"


# ── get_all_manual_articles ──

class TestGetAllManualArticles:
    def test_returns_all_sorted(self, db):
        for added_at, title, url in [
            ("2026-03-28T10:00:00", "Older", "https://a.com/1"),
            ("2026-03-29T10:00:00", "Newer", "https://a.com/2"),
        ]:
            db.table("manual_articles").append({
                "id": "1",
                "added_at": added_at,
                "title": title,
                "url": url,
                "description": "d",
                "added_by": "expert",
            })

        results = get_all_manual_articles(db)
        assert len(results) == 2
        assert results[0]["title"] == "Newer"  # 최신순


# ── manual_reports (PR1: Weekly 수동 보고서) ──


class TestManualReports:
    def test_schema_present(self, db):
        assert "manual_reports" in SHEET_HEADERS
        assert db.table("manual_reports").path.exists()
        # 필수 컬럼 확인
        for col in ("id", "title", "source_type", "url", "file_path",
                    "text_path", "summary"):
            assert col in SHEET_HEADERS["manual_reports"]

    def test_insert_url_report(self, db):
        rid = insert_manual_report(
            db,
            title="IBM AI Index 2026",
            source_type="url",
            url="https://example.com/ibm-ai-index.html",
            summary="76% of enterprises have appointed CAIO...",
        )
        assert isinstance(rid, str) and len(rid) > 0

        rows = db.table("manual_reports").rows()
        assert len(rows) == 1
        assert rows[0]["title"] == "IBM AI Index 2026"
        assert rows[0]["source_type"] == "url"
        assert rows[0]["url"] == "https://example.com/ibm-ai-index.html"
        assert rows[0]["file_path"] == ""

    def test_insert_pdf_report(self, db):
        rid = insert_manual_report(
            db,
            title="Microsoft Q3 FY2026 Earnings",
            source_type="pdf",
            original_filename="msft_q3_fy26.pdf",
            file_path="data/manual_reports/abc123.pdf",
            text_path="data/manual_reports/abc123.txt",
            summary="Cloud+AI revenue $37B, +123% YoY...",
        )
        rows = db.table("manual_reports").rows()
        assert rows[0]["source_type"] == "pdf"
        assert rows[0]["original_filename"] == "msft_q3_fy26.pdf"
        assert rows[0]["file_path"].endswith(".pdf")
        assert str(rows[0]["id"]) == rid

    def test_insert_rejects_invalid_source_type(self, db):
        with pytest.raises(ValueError, match="source_type"):
            insert_manual_report(
                db,
                title="x",
                source_type="other",
                url="https://x.com",
            )

    def test_get_all_sorted_desc(self, db):
        # 시간 순서를 강제하기 위해 직접 row 삽입
        from datetime import datetime as _dt
        for added_at, title in [
            ("2026-05-10T10:00:00", "Older"),
            ("2026-05-12T10:00:00", "Newer"),
        ]:
            db.table("manual_reports").append({
                "id": _dt.now().strftime("%Y%m%d%H%M%S") + title,
                "added_at": added_at,
                "title": title,
                "source_type": "url",
                "url": "https://example.com/" + title,
                "original_filename": "",
                "file_path": "",
                "text_path": "",
                "summary": "",
                "added_by": "user",
            })

        results = get_all_manual_reports(db)
        assert len(results) == 2
        assert results[0]["title"] == "Newer"

    def test_get_manual_report_by_id(self, db):
        rid = insert_manual_report(
            db, title="Sample", source_type="url",
            url="https://example.com/s",
        )
        found = get_manual_report(db, rid)
        assert found is not None
        assert found["title"] == "Sample"
        assert str(found["id"]) == rid

    def test_get_manual_report_missing_returns_none(self, db):
        assert get_manual_report(db, "nonexistent-id") is None

    def test_clear_all_reports(self, db):
        insert_manual_report(db, title="A", source_type="url", url="https://a.com")
        insert_manual_report(db, title="B", source_type="url", url="https://b.com")
        assert len(db.table("manual_reports").rows()) == 2

        deleted = clear_all_manual_reports(db)
        assert deleted == 2
        assert len(db.table("manual_reports").rows()) == 0
