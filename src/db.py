"""src/db.py — 로컬 CSV 파일 기반 데이터 저장소.

이전에 Google Sheets 1개 스프레드시트 + 4개 탭으로 관리하던 데이터를
``data/db/`` 아래 CSV 파일 4개로 옮겼다. 호출자(main.py, web_ui/app.py)가
거의 변경 없이 동작하도록 함수 시그니처는 모두 보존한다.

테이블:
  - daily_articles.csv: GNews 수집 기사
  - manual_articles.csv: 전문가 수동 추가 기사
  - article_archive.csv: 뉴스레터 발송 아카이브
  - newsletter_log.csv: 발송 이력 로그

동시성:
  같은 PC 내에서 cron + web UI 동시 쓰기는 ``_file_lock`` (msvcrt/fcntl
  advisory lock)으로 직렬화한다. PC 간 동기화는 별도 git push로 해결.
"""
import contextlib
import csv
import logging
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)

# 시트별 헤더 정의 (이전 SheetsDB와 동일 — 기존 호출자 호환)
SHEET_HEADERS: dict[str, list[str]] = {
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
    "manual_reports": [
        # PR (Weekly 수동 보고서 추가): URL/PDF 1차 자료 첨부.
        # source_type='url' 이면 (url 컬럼 사용, file_path 빈값),
        # source_type='pdf' 이면 (file_path 사용, url은 다운로드 원본 URL 또는 빈값).
        # text_path: pdfplumber로 추출한 전문(.txt) 경로. summary: Claude 1차 요약.
        "id", "added_at", "title", "source_type",
        "url", "original_filename", "file_path", "text_path",
        "summary", "added_by",
    ],
}


# ── 파일 락 (Windows + POSIX, 표준 라이브러리만 사용) ──

if sys.platform == "win32":
    import msvcrt

    def _lock_acquire(fh):
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _lock_release(fh):
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _lock_acquire(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)

    def _lock_release(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    """advisory 락. PC 내 cron + web UI 동시 쓰기를 직렬화."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as fh:
        _lock_acquire(fh)
        try:
            yield
        finally:
            _lock_release(fh)


# ── ID 생성 ──

def _gen_id() -> str:
    """timestamp 14자 + 4자리 난수.

    멀티 PC + 멀티 프로세스에서도 동일 초당 10000건 이내면 충돌 가능성 0.
    sortable + 읽기 가능한 문자열.
    """
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rand = random.randint(0, 9999)
    return f"{ts}{rand:04d}"


# ── 테이블 추상화 ──

def _coerce_int(v):
    """gspread는 숫자 문자열을 int로 자동 변환했다 — 동일 동작 유지."""
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return v


class _Table:
    """단일 CSV 파일 추상화.

    공개 메서드:
      rows()          — list[dict] (숫자 자동 int 변환)
      column(name)    — list[str]
      append(row)     — 단일 dict 추가
      append_many()   — dict 리스트 추가
      overwrite()     — 전체 덮어쓰기 (헤더 포함)
      delete_where()  — predicate가 True인 row 삭제, 삭제 건수 반환
    """

    def __init__(self, path: Path, headers: list[str], lock_path: Path):
        self.path = path
        self.headers = headers
        self._lock_path = lock_path

    def ensure(self) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.headers)

    def rows(self) -> list[dict]:
        if not self.path.exists():
            return []
        with self.path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [{k: _coerce_int(v) for k, v in r.items()} for r in reader]

    def column(self, name: str) -> list[str]:
        if name not in self.headers or not self.path.exists():
            return []
        with self.path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return [(r.get(name) or "") for r in reader]

    def append(self, row: dict) -> None:
        with _file_lock(self._lock_path):
            with self.path.open("a", newline="", encoding="utf-8") as f:
                csv.DictWriter(
                    f, fieldnames=self.headers, extrasaction="ignore"
                ).writerow(row)

    def append_many(self, rows: Iterable[dict]) -> None:
        rows = list(rows)
        if not rows:
            return
        with _file_lock(self._lock_path):
            with self.path.open("a", newline="", encoding="utf-8") as f:
                csv.DictWriter(
                    f, fieldnames=self.headers, extrasaction="ignore"
                ).writerows(rows)

    def overwrite(self, rows: Iterable[dict]) -> None:
        with _file_lock(self._lock_path):
            with self.path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f, fieldnames=self.headers, extrasaction="ignore"
                )
                writer.writeheader()
                writer.writerows(rows)

    def delete_where(self, predicate) -> int:
        kept: list[dict] = []
        deleted = 0
        for r in self.rows():
            if predicate(r):
                deleted += 1
            else:
                kept.append(r)
        if deleted:
            self.overwrite(kept)
        return deleted


# ── DB 클래스 ──

class FileDB:
    """data_dir 아래 4개 CSV 파일로 구성된 로컬 DB.

    ``check_today_sent`` 가 Gmail Sent를 진실의 원천으로 사용할 수 있도록
    선택적으로 GmailService를 주입할 수 있다. 미주입 시 newsletter_log.csv로
    fallback (단일 PC 환경에서 동작 보장).
    """

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self._lock_path = self.data_dir / ".lock"
        self._tables: dict[str, _Table] = {}
        self._gmail_service = None
        for name, headers in SHEET_HEADERS.items():
            t = _Table(self.data_dir / f"{name}.csv", headers, self._lock_path)
            t.ensure()
            self._tables[name] = t

    def table(self, name: str) -> _Table:
        if name not in self._tables:
            raise KeyError(f"unknown table: {name}")
        return self._tables[name]

    def attach_gmail(self, gmail_service) -> None:
        """``check_today_sent`` 가 Gmail Sent 검색을 사용하도록 주입.

        ``gmail_service`` 는 ``search_sent_today(newsletter_type, date_str) -> bool``
        메서드를 노출해야 한다 (``src.gmail_service.GmailService`` 참고).
        """
        self._gmail_service = gmail_service

    def close(self) -> None:
        """호환성용 no-op."""
        pass


# 후방 호환성 alias (외부에서 ``from src.db import SheetsDB`` 사용 시)
SheetsDB = FileDB


def init_db(data_dir, creds=None) -> FileDB:
    """``data_dir`` 아래 CSV 4개를 보장하고 FileDB 인스턴스를 반환.

    이전 시그니처 ``init_db(spreadsheet_id, creds)``와 인자 위치 호환.
    ``creds``는 PR#2(Gmail dedup) 도입 시 활용 예정이며 현재는 무시된다.
    """
    db = FileDB(data_dir)
    logger.info("DB 초기화 완료: data_dir=%s", db.data_dir)
    return db


# ── 공개 API (시그니처는 기존 db.py와 동일) ──


def insert_daily_articles(db: FileDB, articles: list[dict]) -> int:
    """daily_articles에 기사를 삽입한다. URL 중복은 무시."""
    table = db.table("daily_articles")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    existing_urls = set(table.column("url"))

    new_rows: list[dict] = []
    inserted = 0
    for a in articles:
        if a["url"] in existing_urls:
            continue
        existing_urls.add(a["url"])
        new_rows.append({
            "id": _gen_id(),
            "collected_at": now,
            "title": a["title"],
            "url": a["url"],
            "description": a.get("description", ""),
            "source_name": a.get("source_name", ""),
            "published_at": a["published_at"],
            "used_in": "",
        })
        inserted += 1

    table.append_many(new_rows)
    logger.info("기사 %d건 삽입 (중복 제외)", inserted)
    return inserted


def insert_manual_article(
    db: FileDB, title: str, url: str, description: str = ""
) -> bool:
    """manual_articles에 수동 기사를 추가한다. URL 중복 시 False."""
    table = db.table("manual_articles")
    if url in set(table.column("url")):
        return False

    table.append({
        "id": _gen_id(),
        "added_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "title": title,
        "url": url,
        "description": description,
        "added_by": "expert",
    })
    return True


def get_articles_for_date_range(
    db: FileDB, start_date: str, end_date: str
) -> list[dict]:
    """published_at 기준 [start_date, end_date) 범위 기사 반환."""
    rows = db.table("daily_articles").rows()
    results = [
        r for r in rows
        if str(r.get("published_at", "")) >= start_date
        and str(r.get("published_at", "")) < end_date
    ]
    results.sort(key=lambda r: str(r.get("published_at", "")), reverse=True)
    return results


def get_existing_summaries(db: FileDB, limit: int = 200) -> str:
    """article_archive에서 최근 기사 제목을 반환한다 (중복 배제용)."""
    titles = [t for t in db.table("article_archive").column("article_title") if t]
    return "\n".join(titles[-limit:])


def _check_today_sent_csv(db: FileDB, newsletter_type: str, today: str) -> bool:
    """newsletter_log.csv 기반 오늘 발송 여부 (Gmail 미가용 시 fallback)."""
    rows = db.table("newsletter_log").rows()
    return any(
        str(r.get("type", "")) == newsletter_type
        and str(r.get("status", "")) == "success"
        and str(r.get("sent_at", "")).startswith(today)
        for r in rows
    )


def check_today_sent(db: FileDB, newsletter_type: str) -> bool:
    """오늘 해당 타입 뉴스레터가 발송되었는지 확인한다.

    우선순위:
      1. ``db._gmail_service`` 주입 시 Gmail Sent 검색 (멀티 PC 안전, 진실의 원천)
      2. Gmail 호출 실패하거나 미주입 시 newsletter_log.csv fallback

    Gmail과 CSV 결과가 다르면 warn 로그를 남기고 Gmail 결과를 반환 (CSV는
    PC 간 drift 가능하므로 신뢰도 낮음).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    csv_result = _check_today_sent_csv(db, newsletter_type, today)

    if db._gmail_service is None:
        return csv_result

    try:
        gmail_result = db._gmail_service.search_sent_today(newsletter_type, today)
    except Exception as e:
        logger.warning(
            "Gmail dedup 검색 실패, CSV fallback: %s", e
        )
        return csv_result

    if gmail_result != csv_result:
        logger.warning(
            "dedup 불일치 — Gmail=%s, CSV=%s (type=%s, date=%s). Gmail을 신뢰.",
            gmail_result, csv_result, newsletter_type, today,
        )
    return gmail_result


def log_newsletter(
    db: FileDB,
    newsletter_type: str,
    article_count: int,
    recipient_count: int,
    status: str,
    error_message: str = None,
    drive_doc_id: str = None,
    nlm_notebook: str = None,
) -> None:
    """newsletter_log에 발송 이력을 기록한다."""
    db.table("newsletter_log").append({
        "id": _gen_id(),
        "sent_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "type": newsletter_type,
        "article_count": article_count,
        "recipient_count": recipient_count,
        "status": status,
        "error_message": error_message or "",
        "drive_doc_id": drive_doc_id or "",
        "nlm_notebook": nlm_notebook or "",
    })
    logger.info("뉴스레터 로그 기록: type=%s, status=%s", newsletter_type, status)


def archive_articles(
    db: FileDB,
    newsletter_date: str,
    newsletter_type: str,
    articles_data: list[dict],
    nlm_notebook_id: str = None,
) -> None:
    """article_archive에 기사를 아카이브한다."""
    rows = [
        {
            "id": _gen_id(),
            "newsletter_date": newsletter_date,
            "newsletter_type": newsletter_type,
            "section": a.get("section", ""),
            "article_title": a["title"],
            "article_url": a["url"],
            "nlm_notebook_id": nlm_notebook_id or "",
        }
        for a in articles_data
    ]
    db.table("article_archive").append_many(rows)
    logger.info("아카이브 %d건 저장", len(articles_data))


def get_weekly_articles(db: FileDB, days: int = 7) -> list[dict]:
    """최근 N일간 수집된 daily_articles."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
    rows = db.table("daily_articles").rows()
    results = [r for r in rows if str(r.get("collected_at", "")) >= cutoff]
    results.sort(key=lambda r: str(r.get("published_at", "")), reverse=True)
    return results


# ── Web UI 전용 함수 (인라인 SQL 대체) ──


def get_daily_articles_today(db: FileDB) -> list[dict]:
    """오늘 수집된 daily_articles."""
    today = datetime.now().strftime("%Y-%m-%d")
    rows = db.table("daily_articles").rows()
    results = [
        r for r in rows
        if str(r.get("collected_at", "")).startswith(today)
    ]
    results.sort(key=lambda r: str(r.get("published_at", "")), reverse=True)
    return results


def get_all_manual_articles(db: FileDB) -> list[dict]:
    """모든 수동 추가 기사 (최신순)."""
    rows = db.table("manual_articles").rows()
    rows.sort(key=lambda r: str(r.get("added_at", "")), reverse=True)
    return rows


def clear_today_archive(db: FileDB, target_date: str) -> int:
    """특정 날짜의 article_archive를 삭제한다 (newsletter_log는 보존)."""
    deleted = db.table("article_archive").delete_where(
        lambda r: str(r.get("newsletter_date", "")) == target_date
    )
    logger.info("아카이브 초기화 완료 (%s): %d건 삭제", target_date, deleted)
    return deleted


def clear_today_daily_articles(db: FileDB, target_date: str) -> int:
    """오늘 수집된 daily_articles를 삭제한다."""
    deleted = db.table("daily_articles").delete_where(
        lambda r: str(r.get("collected_at", "")).startswith(target_date)
    )
    logger.info("daily_articles 초기화 완료 (%s): %d건 삭제", target_date, deleted)
    return deleted


def clear_all_manual_articles(db: FileDB) -> int:
    """manual_articles 전체 삭제."""
    table = db.table("manual_articles")
    count = len(table.rows())
    if count:
        table.overwrite([])
    logger.info("manual_articles 전체 삭제: %d건", count)
    return count


# ── manual_reports (Weekly 수동 보고서 추가) ──


def insert_manual_report(
    db: FileDB,
    *,
    title: str,
    source_type: str,
    url: str = "",
    original_filename: str = "",
    file_path: str = "",
    text_path: str = "",
    summary: str = "",
    added_by: str = "user",
    report_id: str | None = None,
) -> str:
    """manual_reports에 1차 자료(URL 또는 PDF) 레코드를 추가한다.

    Args:
        title: 보고서 제목 (HTML/PDF 메타 또는 파일명에서 추출).
        source_type: 'url' (HTML 페이지) 또는 'pdf' (PDF 파일).
        url: 원본 URL. PDF 업로드면 빈 문자열 가능.
        original_filename: 사용자가 업로드한 원본 파일명.
        file_path: data/manual_reports/{id}.pdf 등 로컬 경로.
        text_path: pdfplumber로 추출한 전문 .txt 경로.
        summary: Claude 1차 요약 (1000~1500자). 실패 시 빈 문자열.
        added_by: 추가 주체 ('user' 기본).
        report_id: 명시 ID. 미지정 시 ``_gen_id()`` 자동 생성.

    Returns:
        생성된 보고서 id.
    """
    if source_type not in ("url", "pdf"):
        raise ValueError(f"source_type must be 'url' or 'pdf', got: {source_type!r}")

    rid = report_id or _gen_id()
    db.table("manual_reports").append({
        "id": rid,
        "added_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "title": title,
        "source_type": source_type,
        "url": url,
        "original_filename": original_filename,
        "file_path": file_path,
        "text_path": text_path,
        "summary": summary,
        "added_by": added_by,
    })
    logger.info("수동 보고서 추가: id=%s, type=%s, title=%s", rid, source_type, title[:50])
    return rid


def get_all_manual_reports(db: FileDB) -> list[dict]:
    """모든 수동 보고서를 최신순으로 반환."""
    rows = db.table("manual_reports").rows()
    rows.sort(key=lambda r: str(r.get("added_at", "")), reverse=True)
    return rows


def get_manual_report(db: FileDB, report_id: str) -> dict | None:
    """특정 id의 수동 보고서를 반환. 없으면 None."""
    for r in db.table("manual_reports").rows():
        # _coerce_int가 적용되어 id가 int로 올 수 있으므로 문자열 비교
        if str(r.get("id", "")) == str(report_id):
            return r
    return None


def clear_all_manual_reports(db: FileDB) -> int:
    """manual_reports 전체 삭제 (CSV row만; 파일은 보존)."""
    table = db.table("manual_reports")
    count = len(table.rows())
    if count:
        table.overwrite([])
    logger.info("manual_reports 전체 삭제: %d건", count)
    return count
