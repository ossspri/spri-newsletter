"""scripts/backfill_aprime_articles.py — 5/14~15 A' 기사 daily_articles 백필.

A' 전환(2026-05-14) 이후 daily_articles.csv에 기사가 저장되지 않았던
기간의 백업 마크다운에서 기사를 추출하여 삽입하는 일회성 스크립트.
"""
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.db import init_db, insert_daily_articles
from src.industry_scan_service import extract_article_urls


def main():
    db = init_db(BASE_DIR / "data" / "db")

    for date_str in ["2026-05-14", "2026-05-15"]:
        md_path = BASE_DIR / "data" / "newsletters" / f"daily_{date_str}.md"
        if not md_path.exists():
            print(f"{date_str}: 백업 파일 없음 — 스킵")
            continue

        markdown = md_path.read_text(encoding="utf-8")
        articles = extract_article_urls(markdown)
        ts = f"{date_str}T06:00:00"
        for a in articles:
            a["published_at"] = ts
            a["source_name"] = urlparse(a["url"]).netloc.removeprefix("www.")
            a["description"] = ""

        if articles:
            inserted = insert_daily_articles(db, articles)
            print(f"{date_str}: {inserted}건 삽입 (추출 {len(articles)}건)")
        else:
            print(f"{date_str}: 추출된 기사 0건")


if __name__ == "__main__":
    main()
