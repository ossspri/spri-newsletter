"""src/drive_service.py — Google Drive/Docs API 연동 (구글 문서 생성)

PRD 4.1: 뉴스레터를 구글 문서로 생성하여 지정 Drive 폴더에 저장한다.
PRD 10: Drive 저장 실패 시 로컬 마크다운 백업은 유지, 에러 로그 기록.
"""
import logging

from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# PRD 4.1 명명 규칙
TITLE_TEMPLATES = {
    "daily": "SPRi_일간브리핑_{date}",
    "weekly": "SPRi_주간동향_{date}",
}


class DriveService:
    """Google Drive/Docs API를 사용한 구글 문서 생성 서비스."""

    def __init__(self, credentials):
        """Drive API와 Docs API 서비스를 초기화한다.

        Args:
            credentials: Google OAuth2 Credentials 객체
        """
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.docs_service = build("docs", "v1", credentials=credentials)

    def create_document(
        self,
        markdown_body: str,
        newsletter_type: str,
        date_str: str,
        folder_id: str,
    ) -> str:
        """구글 문서를 생성하고 지정 폴더로 이동한다.

        Args:
            markdown_body: 뉴스레터 마크다운 본문
            newsletter_type: 'daily' 또는 'weekly'
            date_str: 날짜 문자열 (YYYY-MM-DD)
            folder_id: Google Drive 폴더 ID

        Returns:
            생성된 구글 문서 ID

        Raises:
            ValueError: newsletter_type이 유효하지 않을 때
            googleapiclient.errors.HttpError: API 호출 실패 시
        """
        if newsletter_type not in TITLE_TEMPLATES:
            raise ValueError(
                f"유효하지 않은 뉴스레터 타입: {newsletter_type} (daily 또는 weekly만 허용)"
            )

        title = TITLE_TEMPLATES[newsletter_type].format(date=date_str)

        # Step 1: 빈 구글 문서 생성
        doc = self.docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]
        logger.info("구글 문서 생성: title='%s', id=%s", title, doc_id)

        # Step 2: 마크다운 본문 삽입
        requests = [
            {
                "insertText": {
                    "location": {"index": 1},
                    "text": markdown_body,
                }
            }
        ]
        self.docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()
        logger.info("구글 문서 본문 삽입 완료: %s", doc_id)

        # Step 3: 지정 폴더로 이동
        self.drive_service.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents="root",
            fields="id, parents",
        ).execute()
        logger.info("구글 문서 폴더 이동: folder_id=%s", folder_id)

        return doc_id

    def build_title(self, newsletter_type: str, date_str: str) -> str:
        """문서 제목을 생성한다 (PRD 4.1 명명 규칙).

        Args:
            newsletter_type: 'daily' 또는 'weekly'
            date_str: 날짜 문자열 (YYYY-MM-DD)

        Returns:
            생성된 문서 제목
        """
        if newsletter_type not in TITLE_TEMPLATES:
            raise ValueError(
                f"유효하지 않은 뉴스레터 타입: {newsletter_type}"
            )
        return TITLE_TEMPLATES[newsletter_type].format(date=date_str)
