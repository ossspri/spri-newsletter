"""src/manual_reports.py — 수동 보고서(Weekly 첨부) 처리 헬퍼.

Weekly 화면에서 사용자가 URL 또는 PDF 파일로 1차 자료(연구보고서/백서/회사
발표)를 첨부할 때 사용하는 안전 검증 + 파일 처리 유틸 모음.

PR1: URL 안전성 검증, 파일명 sanitize, URL kind 판별 (HTML vs PDF).
PR2: download_pdf, extract_pdf_text, save_report_text.

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

PDF_MAGIC = b"%PDF-"
DEFAULT_MAX_PDF_BYTES = 50 * 1024 * 1024  # 50MB

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


def detect_url_kind(url: str, timeout: float = 10.0, ssl_verify: bool = True) -> str:
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
            verify=ssl_verify,
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


# ── PR2: PDF 다운로드 + 텍스트 추출 + 저장 ──


def download_pdf(
    url: str,
    out_path: Path,
    max_bytes: int = DEFAULT_MAX_PDF_BYTES,
    timeout: float = 30.0,
    ssl_verify: bool = True,
) -> Path:
    """PDF URL을 스트리밍으로 다운로드하여 ``out_path``에 저장한다.

    안전 정책:
      - 첫 청크의 magic byte ``%PDF-`` 검증
      - 누적 바이트 ``max_bytes`` 초과 시 중단 + 부분 파일 삭제
      - 호출 전 ``is_safe_url(url)`` 통과 가정

    Args:
        url: PDF 직링크.
        out_path: 저장 경로. 부모 디렉토리 자동 생성.
        max_bytes: 허용 최대 크기. 초과 시 ``ValueError``.
        timeout: HTTP 타임아웃.

    Returns:
        ``out_path`` (저장 성공 시).

    Raises:
        ValueError: magic byte 불일치 또는 크기 초과.
        requests.RequestException: 네트워크/HTTP 에러.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    resp = requests.get(
        url,
        timeout=timeout,
        stream=True,
        verify=ssl_verify,
        headers={"User-Agent": "Mozilla/5.0 (compatible; SPRi-Newsletter/1.0)"},
    )
    resp.raise_for_status()

    chunk_size = 64 * 1024
    total = 0
    first_chunk = True

    try:
        with out_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                if first_chunk:
                    if not chunk.startswith(PDF_MAGIC):
                        raise ValueError(
                            "다운로드한 파일이 PDF가 아님 (magic byte 불일치)"
                        )
                    first_chunk = False
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(
                        f"PDF 크기 한도 초과: {total} > {max_bytes} bytes"
                    )
                f.write(chunk)
    except Exception:
        # 부분 파일 정리
        out_path.unlink(missing_ok=True)
        raise

    logger.info("PDF 다운로드 완료: %s (%d bytes)", out_path.name, total)
    return out_path


def extract_pdf_text(
    path: Path,
    head_pages: int = 3,
) -> tuple[str, str]:
    """pdfplumber로 PDF에서 전문 + 첫 N페이지 발췌를 추출한다.

    Args:
        path: 로컬 PDF 파일 경로.
        head_pages: 발췌에 포함할 첫 페이지 수 (기본 3).

    Returns:
        ``(full_text, head_excerpt)`` 튜플.
          - ``full_text``: 전 페이지 텍스트, 페이지 사이는 ``\\n\\n`` 구분.
          - ``head_excerpt``: 첫 ``head_pages``개 페이지만.

    Raises:
        FileNotFoundError, RuntimeError (pdfplumber 내부 에러).

    Note: 이미지 스캔 PDF는 텍스트 레이어가 없어 빈 문자열 반환 가능.
    OCR fallback은 범위 밖.
    """
    import pdfplumber  # 지연 import — PR1에서 호출되지 않음

    pages_text: list[str] = []
    head_pages_text: list[str] = []

    with pdfplumber.open(str(path)) as pdf:
        for i, page in enumerate(pdf.pages):
            try:
                text = page.extract_text() or ""
            except Exception as e:
                logger.warning("PDF page %d 추출 실패: %s", i + 1, e)
                text = ""
            pages_text.append(text)
            if i < head_pages:
                head_pages_text.append(text)

    full_text = "\n\n".join(pages_text).strip()
    head_excerpt = "\n\n".join(head_pages_text).strip()
    logger.info(
        "PDF 텍스트 추출: %s (%d pages, %d chars total)",
        path.name, len(pages_text), len(full_text),
    )
    return full_text, head_excerpt


def save_report_text(report_id: str, full_text: str) -> Path:
    """추출한 보고서 전문을 ``data/manual_reports/{id}.txt``에 저장.

    이유: CSV row에 수만자 본문을 넣지 않기 위해 별도 파일로 보관.
    프롬프트는 ``summary`` + ``head_excerpt``만 사용; ``full_text``는
    추후 디버깅/재처리용 보관.
    """
    out_path = MANUAL_REPORTS_DIR / f"{report_id}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_text, encoding="utf-8")
    logger.info("보고서 전문 저장: %s (%d chars)", out_path, len(full_text))
    return out_path
