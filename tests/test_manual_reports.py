"""tests/test_manual_reports.py — 수동 보고서 헬퍼 단위 테스트 (PR1)."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from src.manual_reports import (
    MANUAL_REPORTS_DIR,
    detect_url_kind,
    is_safe_url,
    sanitize_filename,
)


# ── is_safe_url (SSRF 1차 방어) ──


class TestIsSafeUrl:
    def test_https_public_domain_allowed(self):
        # 실제 DNS 해석 — example.com은 공개 IP라 통과해야 함
        assert is_safe_url("https://www.example.com/report.pdf") is True

    def test_http_public_domain_allowed(self):
        assert is_safe_url("http://www.example.com") is True

    def test_localhost_blocked(self):
        assert is_safe_url("http://localhost/admin") is False

    def test_127_loopback_blocked(self):
        assert is_safe_url("http://127.0.0.1/x") is False

    def test_private_10_blocked(self):
        # 10.0.0.1은 DNS 해석 없이 IP 리터럴 → ip_address 분류로 private
        assert is_safe_url("http://10.0.0.1/x") is False

    def test_private_192_blocked(self):
        assert is_safe_url("http://192.168.1.1/x") is False

    def test_private_172_blocked(self):
        assert is_safe_url("http://172.16.0.1/x") is False

    def test_zero_address_blocked(self):
        assert is_safe_url("http://0.0.0.0/x") is False

    def test_link_local_blocked(self):
        assert is_safe_url("http://169.254.169.254/latest/meta-data") is False

    def test_ipv6_loopback_blocked(self):
        assert is_safe_url("http://[::1]/x") is False

    def test_file_scheme_blocked(self):
        assert is_safe_url("file:///etc/passwd") is False

    def test_gopher_scheme_blocked(self):
        assert is_safe_url("gopher://x/y") is False

    def test_empty_url_blocked(self):
        assert is_safe_url("") is False

    def test_none_blocked(self):
        assert is_safe_url(None) is False  # type: ignore[arg-type]

    def test_no_hostname_blocked(self):
        # 'http://' 만 있고 host 없음
        assert is_safe_url("http://") is False

    def test_dns_resolution_failure_blocks(self):
        # 실제로 해석 안 되는 도메인 — 안전을 위해 차단
        assert is_safe_url("http://this-domain-definitely-does-not-exist-12345.invalid") is False


# ── sanitize_filename ──


class TestSanitizeFilename:
    def test_normal_name_preserved(self):
        assert sanitize_filename("report.pdf") == "report.pdf"

    def test_path_traversal_stripped(self):
        # secure_filename은 ../ 등 경로 구분자를 제거
        result = sanitize_filename("../../etc/passwd")
        assert "/" not in result
        assert ".." not in result.replace(".pdf", "")  # 단순 dot은 허용

    def test_windows_path_stripped(self):
        result = sanitize_filename("C:\\Windows\\System32\\evil.exe")
        assert "\\" not in result
        assert ":" not in result

    def test_dangerous_chars_removed(self):
        result = sanitize_filename('report<>:"|?*.pdf')
        # secure_filename은 이런 문자들을 제거 또는 _로 치환
        for ch in '<>:"|?*':
            assert ch not in result

    def test_empty_returns_unnamed(self):
        assert sanitize_filename("") == "unnamed"

    def test_whitespace_only_returns_unnamed(self):
        assert sanitize_filename("   ") == "unnamed"

    def test_long_name_truncated(self):
        long_name = "a" * 300 + ".pdf"
        result = sanitize_filename(long_name, max_length=128)
        assert len(result) <= 128
        assert result.endswith(".pdf")

    def test_none_returns_unnamed(self):
        assert sanitize_filename(None) == "unnamed"  # type: ignore[arg-type]


# ── detect_url_kind ──


class TestDetectUrlKind:
    def test_pdf_path_extension_fast_path(self):
        # 경로가 .pdf로 끝나면 HEAD 요청 없이 즉시 'pdf'
        with patch("src.manual_reports.requests.head") as mock_head:
            result = detect_url_kind("https://example.com/path/report.pdf")
            assert result == "pdf"
            mock_head.assert_not_called()

    def test_html_content_type(self):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        with patch("src.manual_reports.requests.head", return_value=mock_resp):
            assert detect_url_kind("https://example.com/page") == "html"

    def test_pdf_content_type(self):
        mock_resp = MagicMock()
        mock_resp.headers = {"Content-Type": "application/pdf"}
        with patch("src.manual_reports.requests.head", return_value=mock_resp):
            assert detect_url_kind("https://example.com/file") == "pdf"

    def test_octet_stream_with_pdf_disposition(self):
        mock_resp = MagicMock()
        mock_resp.headers = {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="report.pdf"',
        }
        with patch("src.manual_reports.requests.head", return_value=mock_resp):
            assert detect_url_kind("https://example.com/file") == "pdf"

    def test_head_failure_falls_back_to_html(self):
        import requests as _req
        with patch("src.manual_reports.requests.head", side_effect=_req.ConnectionError("x")):
            assert detect_url_kind("https://example.com/page") == "html"


# ── 디렉토리 상수 ──


class TestConstants:
    def test_reports_dir_under_data(self):
        assert MANUAL_REPORTS_DIR.parts[0] == "data"
        assert MANUAL_REPORTS_DIR.name == "manual_reports"
