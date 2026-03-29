"""src/db.py — SQLite 데이터베이스 관리 (기사 아카이브, 발송 이력)"""
import sqlite3
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS daily_articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    collected_at  TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    description   TEXT,
    source_name   TEXT,
    published_at  TEXT NOT NULL,
    used_in       TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS manual_articles (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    added_at      TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL UNIQUE,
    description   TEXT,
    added_by      TEXT DEFAULT 'expert'
);

CREATE TABLE IF NOT EXISTS article_archive (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    newsletter_date TEXT NOT NULL,
    newsletter_type TEXT NOT NULL,
    section         TEXT,
    article_title   TEXT NOT NULL,
    article_url     TEXT NOT NULL,
    nlm_notebook_id TEXT
);

CREATE TABLE IF NOT EXISTS newsletter_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at         TEXT NOT NULL,
    type            TEXT NOT NULL,
    article_count   INTEGER,
    recipient_count INTEGER,
    status          TEXT NOT NULL,
    error_message   TEXT DEFAULT NULL,
    drive_doc_id    TEXT DEFAULT NULL,
    nlm_notebook    TEXT DEFAULT NULL
);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    logger.info("DB 초기화 완료: %s", db_path)
    return conn


def insert_daily_articles(conn: sqlite3.Connection, articles: list[dict]) -> int:
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    inserted = 0
    for a in articles:
        try:
            conn.execute(
                "INSERT INTO daily_articles (collected_at, title, url, description, source_name, published_at) VALUES (?, ?, ?, ?, ?, ?)",
                (now, a["title"], a["url"], a.get("description", ""),
                 a.get("source_name", ""), a["published_at"]),
            )
            inserted += 1
        except sqlite3.IntegrityError:
            pass  # URL 중복 무시
    conn.commit()
    logger.info("기사 %d건 삽입 (중복 제외)", inserted)
    return inserted


def insert_manual_article(conn: sqlite3.Connection, title: str, url: str, description: str = "") -> bool:
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        conn.execute(
            "INSERT INTO manual_articles (added_at, title, url, description) VALUES (?, ?, ?, ?)",
            (now, title, url, description),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_articles_for_date_range(conn: sqlite3.Connection, start_date: str, end_date: str) -> list[dict]:
    cursor = conn.execute(
        "SELECT id, collected_at, title, url, description, source_name, published_at, used_in "
        "FROM daily_articles WHERE published_at >= ? AND published_at < ? ORDER BY published_at DESC",
        (start_date, end_date),
    )
    return [
        {"id": r[0], "collected_at": r[1], "title": r[2], "url": r[3],
         "description": r[4], "source_name": r[5], "published_at": r[6], "used_in": r[7]}
        for r in cursor.fetchall()
    ]


def get_existing_summaries(conn: sqlite3.Connection, limit: int = 200) -> str:
    cursor = conn.execute(
        "SELECT article_title FROM article_archive ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    titles = [row[0] for row in cursor.fetchall()]
    return "\n".join(titles)


def check_today_sent(conn: sqlite3.Connection, newsletter_type: str) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    cursor = conn.execute(
        "SELECT COUNT(*) FROM newsletter_log WHERE type = ? AND status = 'success' AND sent_at LIKE ?",
        (newsletter_type, f"{today}%"),
    )
    return cursor.fetchone()[0] > 0


def log_newsletter(
    conn: sqlite3.Connection,
    newsletter_type: str,
    article_count: int,
    recipient_count: int,
    status: str,
    error_message: str = None,
    drive_doc_id: str = None,
    nlm_notebook: str = None,
) -> None:
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    conn.execute(
        "INSERT INTO newsletter_log (sent_at, type, article_count, recipient_count, status, error_message, drive_doc_id, nlm_notebook) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (now, newsletter_type, article_count, recipient_count, status,
         error_message, drive_doc_id, nlm_notebook),
    )
    conn.commit()
    logger.info("뉴스레터 로그 기록: type=%s, status=%s", newsletter_type, status)


def archive_articles(
    conn: sqlite3.Connection,
    newsletter_date: str,
    newsletter_type: str,
    articles_data: list[dict],
    nlm_notebook_id: str = None,
) -> None:
    for a in articles_data:
        conn.execute(
            "INSERT INTO article_archive (newsletter_date, newsletter_type, section, article_title, article_url, nlm_notebook_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (newsletter_date, newsletter_type, a.get("section", ""),
             a["title"], a["url"], nlm_notebook_id),
        )
    conn.commit()
    logger.info("아카이브 %d건 저장", len(articles_data))


def get_weekly_articles(conn: sqlite3.Connection, days: int = 7) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    cursor = conn.execute(
        "SELECT id, collected_at, title, url, description, source_name, published_at, used_in "
        "FROM daily_articles WHERE collected_at >= ? ORDER BY published_at DESC",
        (cutoff,),
    )
    return [
        {"id": r[0], "collected_at": r[1], "title": r[2], "url": r[3],
         "description": r[4], "source_name": r[5], "published_at": r[6], "used_in": r[7]}
        for r in cursor.fetchall()
    ]
