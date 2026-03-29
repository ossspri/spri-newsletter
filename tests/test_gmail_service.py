"""tests/test_gmail_service.py — Gmail API 발송 서비스 TDD 테스트"""
import base64
from email.mime.multipart import MIMEMultipart
from unittest.mock import patch, MagicMock, call

import pytest

from src.gmail_service import GmailService


@pytest.fixture
def mock_credentials():
    return MagicMock()


@pytest.fixture
def mock_gmail_api():
    """Gmail API 서비스 mock."""
    mock_service = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {
        "id": "msg_123",
        "threadId": "thread_456",
        "labelIds": ["SENT"],
    }
    mock_service.users.return_value.messages.return_value.send.return_value = mock_send
    return mock_service


SAMPLE_RECIPIENTS = ["analyst1@spri.kr", "analyst2@spri.kr"]
SAMPLE_SUBJECT = "[Daily] 글로벌 SW산업동향 (2026-03-29)"
SAMPLE_HTML = "<html><body><h1>Test Newsletter</h1></body></html>"


class TestGmailServiceInit:
    """GmailService 초기화 테스트."""

    @patch("src.gmail_service.build")
    def test_builds_gmail_service(self, mock_build, mock_credentials):
        """gmail v1 서비스를 빌드한다."""
        GmailService(mock_credentials)
        mock_build.assert_called_once_with("gmail", "v1", credentials=mock_credentials)

    @patch("src.gmail_service.build")
    def test_stores_service(self, mock_build, mock_credentials):
        """빌드된 서비스를 저장한다."""
        mock_svc = MagicMock()
        mock_build.return_value = mock_svc
        gmail = GmailService(mock_credentials)
        assert gmail.service == mock_svc


class TestSendEmail:
    """이메일 발송 테스트."""

    @patch("src.gmail_service.build")
    def test_send_email_success(self, mock_build, mock_credentials, mock_gmail_api):
        """정상 발송 시 API 응답을 반환한다."""
        mock_build.return_value = mock_gmail_api
        gmail = GmailService(mock_credentials)

        result = gmail.send_email(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        assert result["id"] == "msg_123"
        assert result["threadId"] == "thread_456"

    @patch("src.gmail_service.build")
    def test_send_email_calls_api_with_raw(self, mock_build, mock_credentials, mock_gmail_api):
        """base64 인코딩된 raw 메시지로 API를 호출한다."""
        mock_build.return_value = mock_gmail_api
        gmail = GmailService(mock_credentials)

        gmail.send_email(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        send_call = mock_gmail_api.users().messages().send
        send_call.assert_called_once()
        call_kwargs = send_call.call_args
        assert call_kwargs[1]["userId"] == "me"
        assert "raw" in call_kwargs[1]["body"]

    @patch("src.gmail_service.build")
    def test_send_email_empty_recipients_raises(self, mock_build, mock_credentials):
        """수신자가 비어있으면 ValueError."""
        gmail = GmailService(mock_credentials)

        with pytest.raises(ValueError, match="수신자 목록이 비어있습니다"):
            gmail.send_email([], SAMPLE_SUBJECT, SAMPLE_HTML)

    @patch("src.gmail_service.build")
    def test_send_email_single_recipient(self, mock_build, mock_credentials, mock_gmail_api):
        """수신자 1명도 정상 동작한다."""
        mock_build.return_value = mock_gmail_api
        gmail = GmailService(mock_credentials)

        result = gmail.send_email(["single@test.com"], SAMPLE_SUBJECT, SAMPLE_HTML)
        assert result["id"] == "msg_123"

    @patch("src.gmail_service.build")
    def test_send_email_custom_sender(self, mock_build, mock_credentials, mock_gmail_api):
        """커스텀 sender를 전달할 수 있다."""
        mock_build.return_value = mock_gmail_api
        gmail = GmailService(mock_credentials)

        gmail.send_email(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML, sender="custom@test.com")

        send_call = mock_gmail_api.users().messages().send
        assert send_call.call_args[1]["userId"] == "custom@test.com"

    @patch("src.gmail_service.build")
    def test_send_email_api_error_propagates(self, mock_build, mock_credentials):
        """API 오류는 그대로 전파한다."""
        mock_service = MagicMock()
        mock_service.users().messages().send().execute.side_effect = Exception("API Error")
        mock_build.return_value = mock_service
        gmail = GmailService(mock_credentials)

        with pytest.raises(Exception, match="API Error"):
            gmail.send_email(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)


class TestBuildMimeMessage:
    """MIME 메시지 구성 테스트."""

    @patch("src.gmail_service.build")
    def test_mime_has_correct_to_header(self, mock_build, mock_credentials):
        """To 헤더에 수신자가 콤마로 결합된다."""
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        assert msg["To"] == "analyst1@spri.kr, analyst2@spri.kr"

    @patch("src.gmail_service.build")
    def test_mime_has_correct_subject(self, mock_build, mock_credentials):
        """Subject 헤더가 정확하다."""
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        assert msg["Subject"] == SAMPLE_SUBJECT

    @patch("src.gmail_service.build")
    def test_mime_contains_html_body(self, mock_build, mock_credentials):
        """HTML 본문이 MIME에 포함된다."""
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        payload = msg.get_payload()
        assert len(payload) == 1
        assert payload[0].get_content_type() == "text/html"

    @patch("src.gmail_service.build")
    def test_mime_html_charset_utf8(self, mock_build, mock_credentials):
        """HTML 파트 charset이 utf-8이다."""
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        payload = msg.get_payload()
        assert payload[0].get_charset() is not None

    @patch("src.gmail_service.build")
    def test_mime_is_multipart_alternative(self, mock_build, mock_credentials):
        """메시지가 multipart/alternative 타입이다."""
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(SAMPLE_RECIPIENTS, SAMPLE_SUBJECT, SAMPLE_HTML)

        assert msg.get_content_type() == "multipart/alternative"

    @patch("src.gmail_service.build")
    def test_mime_korean_subject(self, mock_build, mock_credentials):
        """한국어 제목이 정상 처리된다."""
        korean_subject = "[Daily] 글로벌 SW산업동향 (2026-03-29)"
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(["test@test.com"], korean_subject, SAMPLE_HTML)

        assert msg["Subject"] == korean_subject

    @patch("src.gmail_service.build")
    def test_mime_korean_html_body(self, mock_build, mock_credentials):
        """한국어 HTML 본문이 정상 인코딩된다."""
        korean_html = "<html><body><h1>소프트웨어정책연구소</h1></body></html>"
        gmail = GmailService(mock_credentials)
        msg = gmail._build_mime_message(["test@test.com"], "Test", korean_html)

        payload = msg.get_payload()
        # decode해서 한국어가 포함되어 있는지 확인
        decoded = payload[0].get_payload(decode=True).decode("utf-8")
        assert "소프트웨어정책연구소" in decoded
