"""src/utils.py — 유틸리티 (retry, KST 날짜, 마크다운→HTML 변환)"""
import functools
import logging
import re
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


# ── retry 데코레이터 ──

def retry(max_retries: int = 3, delay: float = 30):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    logger.warning(
                        "[재시도 %d/%d] %s: %s", attempt, max_retries,
                        func.__name__, e,
                    )
                    if attempt < max_retries:
                        time.sleep(delay)
            raise last_exc
        return wrapper
    return decorator


# ── KST 날짜 헬퍼 ──

def get_kst_now() -> str:
    return datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")


def get_kst_date_str() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def get_kst_24h_ago_utc() -> str:
    utc_now = datetime.now(timezone.utc)
    ago = utc_now - timedelta(hours=24)
    return ago.strftime("%Y-%m-%dT%H:%M:%SZ")


def get_week_monday_str(date_str: str) -> str:
    """주어진 날짜가 속한 주의 월요일을 MMDD 형식으로 반환."""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%m%d")


def get_kst_display_date() -> str:
    """'2026년 3월 29일 일요일' 형식."""
    now = datetime.now(KST)
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    return f"{now.year}년 {now.month}월 {now.day}일 {weekdays[now.weekday()]}"


# ── 마크다운 → HTML 변환 ──
# reference/runDailyAutomation.js:209-216 정규식 체인 보존
# 색상만 PRD 5.2로 변경: #1a73e8 → #1a2a3a (헤더), #2d5a8e (액센트)

def markdown_to_html(markdown: str) -> str:
    html = markdown

    # ## 섹션 헤더
    html = re.sub(
        r'^## (.*$)',
        r'<h2 style="color:#1a2a3a; font-weight:bold; border-bottom:2px solid #2d5a8e; padding-bottom:6px; margin-top:25px; margin-bottom:10px;">\1</h2>',
        html,
        flags=re.MULTILINE,
    )

    # * [title](url) — 소스 링크
    html = re.sub(
        r'^\* \[(.+?)\]\((.+?)\)',
        r'<p style="font-size:13px; color:#888; margin:4px 0 12px 0;">📎 <a href="\2" target="_blank" style="color:#2d5a8e; text-decoration:none;">\1</a></p>',
        html,
        flags=re.MULTILINE,
    )

    # 인라인 [text](url)
    html = re.sub(
        r'\[(.+?)\]\((.+?)\)',
        r'<a href="\2" target="_blank" style="color:#2d5a8e; text-decoration:none;">\1</a>',
        html,
    )

    # **볼드**
    html = re.sub(
        r'\*\*(.+?)\*\*',
        r'<strong style="color:#1a2a3a;">\1</strong>',
        html,
    )

    # ---
    html = re.sub(
        r'---',
        r'<hr style="border:0; border-top:1px solid #eee; margin:20px 0;">',
        html,
    )

    # 줄바꿈
    html = html.replace('\n', '<br>')

    # 블록 요소 뒤 불필요한 <br> 제거
    html = re.sub(r'(</h2>|</h3>|</p>|</hr>)<br>', r'\1', html)

    return html
