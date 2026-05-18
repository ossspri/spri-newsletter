"""src/gmail_service.py — Gmail API 이메일 발송 (OAuth2 + HTML 메일)

PRD 5.1: Gmail API를 통해 Daily/Weekly 수신자에게 HTML 이메일을 발송한다.
PRD 10: Gmail 발송 실패 시 SQLite newsletter_log에 실패 기록.
reference/runDailyAutomation.js:18 GmailApp.sendEmail() → Gmail API 마이그레이션.
"""
import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httplib2
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)


class GmailService:
    """Gmail API를 사용한 이메일 발송 서비스."""

    def __init__(self, credentials, ssl_verify: bool = True):
        """Gmail API 서비스를 초기화한다.

        Args:
            credentials: Google OAuth2 Credentials 객체
            ssl_verify: False면 SSL 인증서 검증 비활성화 (사내 프록시용)
        """
        if not ssl_verify:
            http = httplib2.Http(disable_ssl_certificate_validation=True)
            authed_http = AuthorizedHttp(credentials, http=http)
            self.service = build("gmail", "v1", http=authed_http)
        else:
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

    def search_sent_today(self, newsletter_type: str, date_str: str) -> bool:
        """오늘자 동일 제목 메일이 Gmail Sent에 이미 있는지 확인한다.

        멀티 PC 환경에서 ``check_today_sent`` 의 진실의 원천. 로컬 CSV는 PC 간
        drift할 수 있지만 Gmail Sent는 공유 계정 기준 단일 source.

        쿼리: ``from:me subject:"<예상 제목>" newer_than:2d``
          - ``from:me``: 인증된 계정이 보낸 것만 (공유 계정에서 다른 멤버가 보낸
            무관한 메일을 false positive로 잡지 않게 함)
          - subject: ``build_email_subject``의 정확한 prefix + 날짜 매칭
          - ``newer_than:2d``: 검색 범위 한정용 (제목에 날짜가 있어
            오래된 같은 날짜 메일을 잡을 일은 사실상 없음)

        Args:
            newsletter_type: 'daily' | 'weekly'
            date_str: 'YYYY-MM-DD' (KST 기준 오늘 날짜)

        Returns:
            동일 제목 메일이 1건 이상이면 True.
        """
        # 순환 import 방지 위해 함수 내 import.
        from src.email_template import build_email_subject

        subject = build_email_subject(newsletter_type, date_str)
        query = f'from:me subject:"{subject}" newer_than:2d'

        result = (
            self.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=1)
            .execute()
        )
        found = bool(result.get("messages"))
        logger.debug(
            "Gmail Sent dedup 검색: query=%s, found=%s", query, found
        )
        return found
