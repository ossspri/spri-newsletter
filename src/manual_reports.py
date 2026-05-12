"""src/manual_reports.py — 수동 보고서(Weekly 첨부) 처리 헬퍼.

Weekly 화면에서 사용자가 URL 또는 PDF 파일로 1차 자료(연구보고서/백서/회사
발표)를 첨부할 때 사용하는 안전 검증 + 파일 처리 유틸 모음.

PR1 범위: URL 안전성 검증, 파일명 sanitize, URL kind 판별 (HTML vs PDF).
PR2 범위 (별도 commit): download_pdf, extract_pdf_text, save_report_text.

호출자: web_ui/app.py의 /weekly/add-report 라우트.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse

import requests
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# 보고서 파일 저장 디렉토리 — PDF 원본과 추출 텍스트가 함께 들어감.
# 호출자는 ``MANUAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)`` 보장 필요.
MANUAL_REPORTS_DIR = Path("data") / "manual_reports"


def is_safe_url(url: str) -> bool:
    """외부 호출에 안전한 URL인지 검사 (SSRF 1차 방어).

    차단 조건:
      - http/https 외 스킴 (file://, gopher:// 등)
      - hostname이 없거나 빈 문자열
      - DNS 해석 결과가 loopback / private / link-local / reserved IP
      - 호스트명이 'localhost' 또는 '0.0.0.0'

    한계: **DNS 재바인딩 공격은 막지 못함**. 검증 시점과 실제 fetch 시점
    사이에 DNS가 바뀌면 우회 가능. 1차 PR에서는 best-effort로 받아들임.
    필요 시 호출자에서 fetch 직전 재검증 또는 IP 고정 정책 추가.
    """
    if not isinstance(url, str) or not url:
        return False

    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # 명시적 위험 호스트
    lowered = hostname.lower()
    if lowered in ("localhost", "0.0.0.0", "::", "::1"):
        return False

    # DNS 해석 — getaddrinfo는 IPv4/IPv6 모두 반환
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError) as e:
        # 해석 실패 시 안전하게 차단 — 실제 fetch도 어차피 실패할 것
        logger.debug("is_safe_url: DNS 해석 실패 (%s): %s", hostname, e)
        return False

    for family, _, _, _, sockaddr in infos:
        ip_str = sockaddr[0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            return False

    return True


def sanitize_filename(name: str, max_length: int = 128) -> str:
    """파일명을 안전하게 정제한다.

    werkzeug.utils.secure_filename을 사용하여:
      - 경로 구분자(/, \\) 제거
      - 위험 문자(:, *, ?, ", <, >, |) 제거
      - 유니코드 → ASCII 근사
      - 빈 결과 시 'unnamed' 반환

    Args:
        name: 사용자 입력 원본 파일명.
        max_length: 최대 길이 (확장자 포함). 너무 긴 파일명 방지.

    Returns:
        OS·CSV에 안전한 파일명. 한국어는 영문 대체되거나 제거될 수 있음.
    """
    if not isinstance(name, str) or not name.strip():
        return "unnamed"

    cleaned = secure_filename(name) or "unnamed"
    if len(cleaned) > max_length:
        # 확장자 보존하면서 길이 제한
        p = Path(cleaned)
        ext = p.suffix
        stem = p.stem[: max(1, max_length - len(ext))]
        cleaned = stem + ext
    return cleaned


def detect_url_kind(url: str, timeout: float = 10.0) -> str:
    """URL의 컨텐츠 종류를 ``'html'`` 또는 ``'pdf'``로 판별한다.

    1차로 URL 경로가 .pdf로 끝나면 즉시 'pdf' 반환 (네트워크 부담 회피).
    그렇지 않으면 HEAD 요청으로 Content-Type 확인. 'application/pdf' 또는
    'application/octet-stream' + 파일명 .pdf면 'pdf', 외에는 'html'.

    Args:
        url: 검사할 URL. 호출 전 ``is_safe_url(url)`` 통과 가정.
        timeout: HEAD 요청 타임아웃 초.

    Returns:
        'pdf' | 'html'. HEAD 실패 시 'html'로 fallback (이후 HTML 파싱이
        실패하면 호출자가 자연스럽게 에러 처리).
    """
    if not isinstance(url, str) or not url:
        return "html"

    # 경로 기반 빠른 판단
    parsed = urlparse(url)
    if parsed.path.lower().endswith(".pdf"):
        return "pdf"

    # Content-Type HEAD 요청
    try:
        resp = requests.head(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SPRi-Newsletter/1.0)"},
        )
    except requests.RequestException as e:
        logger.debug("detect_url_kind: HEAD 실패 (%s) — html fallback: %s", url, e)
        return "html"

    content_type = (resp.headers.get("Content-Type") or "").lower().split(";")[0].strip()
    if content_type == "application/pdf":
        return "pdf"

    # 일부 서버가 octet-stream으로 PDF를 내려주는 경우 — URL 후보 재확인
    if content_type == "application/octet-stream":
        disposition = resp.headers.get("Content-Disposition", "")
        if ".pdf" in disposition.lower():
            return "pdf"

    return "html"
