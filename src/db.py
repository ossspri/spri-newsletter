"""src/db.py — Google Sheets 데이터 관리 (기사 아카이브, 발송 이력)

하나의 Google Sheets 스프레드시트에 4개 시트 탭으로 데이터를 관리한다:
  - daily_articles: GNews 수집 기사
  - manual_articles: 전문가 수동 추가 기사
  - article_archive: 뉴스레터 발송 아카이브
  - newsletter_log: 발송 이력 로그
"""
import logging
import time
from datetime import datetime, timedelta

import gspread
from gspread.exceptions import APIError

logger = logging.getLogger(__name__)

# 시트별 헤더 정의
SHEET_HEADERS = {
    "daily_articles": [
        "id", "collected_at", "title", "url", "description",
        "source_name", "published_at", "used_in",
    ],
    "manual_articles": [
        "id", "added_at", "title", "url", "description", "added_by",
    ],
    "article_archive": [
        "id", "newsletter_date", "newsletter_type", "section",
        "article_title", "article_url", "nlm_notebook_id",
    ],
    "newsletter_log": [
        "id", "sent_at", "type", "article_count", "recipient_count",
        "status", "error_message", "drive_doc_id", "nlm_notebook",
    ],
}


def _retry(func, *args, max_retries=3, **kwargs):
    """Google Sheets API 429 에러 시 재시도."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except APIError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise


class SheetsDB:
    """Google Sheets 연결 래퍼 — sqlite3.Connection 대체."""

    def __init__(self, creds, spreadsheet_id: str):
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open_by_key(spreadsheet_id)
        self._sheets: dict[str, gspread.Worksheet] = {}

    def worksheet(self, name: str) -> gspread.Worksheet:
        if name not in self._sheets:
            self._sheets[name] = self.spreadsheet.worksheet(name)
        return self._sheets[name]

    def close(self):
        """호환성용 no-op. 호출자가 conn.close() 호출 시 무시."""
        pass


def init_db(spreadsheet_id: str, creds=None) -> SheetsDB:
    """Google Sheets 스프레드시트를 초기화한다.

    각 시트 탭이 없으면 생성하고, 헤더 행을 설정한다.
    """
    db = SheetsDB(creds, spreadsheet_id)

    existing = {ws.title for ws in db.spreadsheet.worksheets()}
    for sheet_name, headers in SHEET_HEADERS.items():
        if sheet_name not in existing:
            ws = db.spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=len(headers)
            )
            ws.append_row(headers, value_input_option="RAW")
            logger.info("시트 생성: %s", sheet_name)
        else:
            ws = db.spreadsheet.worksheet(sheet_name)
            first_row = ws.row_values(1)
            if first_row != headers:
                ws.update(range_name="A1", values=[headers])
                logger.info("시트 헤더 업데이트: %s", sheet_name)
        db._sheets[sheet_name] = ws

    # 기본 Sheet1 제거 (빈 시트가 남아있으면)
    for ws in db.spreadsheet.worksheets():
        if ws.title not in SHEET_HEADERS and ws.title == "Sheet1":
            try:
                db.spreadsheet.del_worksheet(ws)
            except Exception:
                pass

    logger.info("DB 초기화 완료: spreadsheet_id=%s", spreadsheet_id)
    return db


def _next_id(ws: gspread.Worksheet) -> int:
    """시트의 다음 auto-increment ID를 계산한다."""
    id_col = ws.col_values(1)  # 'id' 헤더 포함
    if len(id_col) <= 1:
        return 1
    try:
        return max(int(v) for v in id_col[1:] if v) + 1
    except ValueError:
        return 1


def _get_all_records(ws: gspread.Worksheet) -> list[dict]:
    """시트의 모든 행을 dict 리스트로 반환한다."""
    return _retry(ws.get_all_records)


def insert_daily_articles(db: SheetsDB, articles: list[dict]) -> int:
    """daily_articles 시트에 기사를 삽입한다. URL 중복은 무시."""
    ws = db.worksheet("daily_articles")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # 기존 URL 목록으로 중복 체크
    existing_urls = set(ws.col_values(4)[1:])  # 4번째 열 = url

    rows_to_add = []
    next_id = _next_id(ws)
    inserted = 0
    for a in articles:
        if a["url"] in existing_urls:
            continue
        existing_urls.add(a["url"])
        rows_to_add.append([
            next_id, now, a["title"], a["url"],
            a.get("description", ""), a.get("source_name", ""),
            a["published_at"], "",
        ])
        next_id += 1
        inserted += 1

    if rows_to_add:
        _retry(ws.append_rows, rows_to_add, value_input_option="RAW")

    logger.info("기사 %d건 삽입 (중복 제외)", inserted)
    return inserted


def insert_manual_article(
    db: SheetsDB, title: str, url: str, description: str = ""
) -> bool:
    """manual_articles 시트에 수동 기사를 추가한다. URL 중복 시 False."""
    ws = db.worksheet("manual_articles")
    existing_urls = set(ws.col_values(4)[1:])  # 4번째 열 = url

    if url in existing_urls:
        return False

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    next_id = _next_id(ws)
    _retry(
        ws.append_row,
        [next_id, now, title, url, description, "expert"],
        value_input_option="RAW",
    )
    return True


def get_articles_for_date_range(
    db: SheetsDB, start_date: str, end_date: str
) -> list[dict]:
    """published_at 기준으로 날짜 범위 내 기사를 반환한다."""
    ws = db.worksheet("daily_articles")
    records = _get_all_records(ws)
    results = [
        r for r in records
        if r.get("published_at", "") >= start_date
        and r.get("published_at", "") < end_date
    ]
    results.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return results


def get_existing_summaries(db: SheetsDB, limit: int = 200) -> str:
    """article_archive에서 최근 기사 제목을 반환한다 (중복 배제용)."""
    ws = db.worksheet("article_archive")
    title_col = ws.col_values(5)  # 5번째 열 = article_title
    titles = title_col[1:]  # 헤더 제외
    return "\n".join(titles[-limit:])


def check_today_sent(db: SheetsDB, newsletter_type: str) -> bool:
    """오늘 해당 타입 뉴스레터가 성공적으로 발송되었는지 확인한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    ws = db.worksheet("newsletter_log")
    records = _get_all_records(ws)
    return any(
        str(r.get("type", "")) == newsletter_type
        and str(r.get("status", "")) == "success"
        and str(r.get("sent_at", "")).startswith(today)
        for r in records
    )


def log_newsletter(
    db: SheetsDB,
    newsletter_type: str,
    article_count: int,
    recipient_count: int,
    status: str,
    error_message: str = None,
    drive_doc_id: str = None,
    nlm_notebook: str = None,
) -> None:
    """newsletter_log 시트에 발송 이력을 기록한다."""
    ws = db.worksheet("newsletter_log")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    next_id = _next_id(ws)
    _retry(
        ws.append_row,
        [
            next_id, now, newsletter_type, article_count, recipient_count,
            status, error_message or "", drive_doc_id or "", nlm_notebook or "",
        ],
        value_input_option="RAW",
    )
    logger.info("뉴스레터 로그 기록: type=%s, status=%s", newsletter_type, status)


def archive_articles(
    db: SheetsDB,
    newsletter_date: str,
    newsletter_type: str,
    articles_data: list[dict],
    nlm_notebook_id: str = None,
) -> None:
    """article_archive 시트에 기사를 아카이브한다."""
    ws = db.worksheet("article_archive")
    next_id = _next_id(ws)

    rows = []
    for a in articles_data:
        rows.append([
            next_id, newsletter_date, newsletter_type,
            a.get("section", ""), a["title"], a["url"],
            nlm_notebook_id or "",
        ])
        next_id += 1

    if rows:
        _retry(ws.append_rows, rows, value_input_option="RAW")
    logger.info("아카이브 %d건 저장", len(articles_data))


def get_weekly_articles(db: SheetsDB, days: int = 7) -> list[dict]:
    """최근 N일간 수집된 daily_articles를 반환한다."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    ws = db.worksheet("daily_articles")
    records = _get_all_records(ws)
    results = [r for r in records if r.get("collected_at", "") >= cutoff]
    results.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return results


# ── Web UI 전용 함수 (인라인 SQL 대체) ──


def get_daily_articles_today(db: SheetsDB) -> list[dict]:
    """오늘 수집된 daily_articles를 반환한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    ws = db.worksheet("daily_articles")
    records = _get_all_records(ws)
    results = [
        r for r in records
        if str(r.get("collected_at", "")).startswith(today)
    ]
    results.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return results


def get_all_manual_articles(db: SheetsDB) -> list[dict]:
    """모든 수동 추가 기사를 반환한다 (최신순)."""
    ws = db.worksheet("manual_articles")
    records = _get_all_records(ws)
    records.sort(key=lambda r: r.get("added_at", ""), reverse=True)
    return records
