"""src/gmail_service.py — Gmail API 이메일 발송 (OAuth2 + HTML 메일)

PRD 5.1: Gmail API를 통해 Daily/Weekly 수신자에게 HTML 이메일을 발송한다.
PRD 10: Gmail 발송 실패 시 SQLite newsletter_log에 실패 기록.
reference/runDailyAutomation.js:18 GmailApp.sendEmail() → Gmail API 마이그레이션.
"""
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailService:
    """Gmail API를 사용한 이메일 발송 서비스."""

    def __init__(self, credentials):
        """Gmail API 서비스를 초기화한다.

        Args:
            credentials: Google OAuth2 Credentials 객체
        """
        self.service = build("gmail", "v1", credentials=credentials)

    def send_email(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
        sender: str = "me",
    ) -> dict:
        """HTML 이메일을 발송한다.

        Args:
            recipients: 수신자 이메일 주소 목록
            subject: 이메일 제목
            html_body: HTML 본문
            sender: 발신자 ('me'는 인증된 계정)

        Returns:
            Gmail API 응답 dict (id, threadId, labelIds)

        Raises:
            ValueError: recipients가 비어있을 때
            googleapiclient.errors.HttpError: API 호출 실패 시
        """
        if not recipients:
            raise ValueError("수신자 목록이 비어있습니다.")

        message = self._build_mime_message(recipients, subject, html_body)
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        result = (
            self.service.users()
            .messages()
            .send(userId=sender, body={"raw": raw})
            .execute()
        )

        logger.info(
            "이메일 발송 완료: subject='%s', recipients=%d명, message_id=%s",
            subject,
            len(recipients),
            result.get("id", ""),
        )
        return result

    def _build_mime_message(
        self,
        recipients: list[str],
        subject: str,
        html_body: str,
    ) -> MIMEMultipart:
        """MIME 메시지를 생성한다."""
        msg = MIMEMultipart("alternative")
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))
        return msg
