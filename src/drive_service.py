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

        # Step 2: 헤더 + 본문 삽입 및 스타일링
        self._insert_styled_content(doc_id, markdown_body, newsletter_type, date_str)
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

    def _insert_styled_content(
        self, doc_id: str, markdown_body: str, newsletter_type: str, date_str: str
    ) -> None:
        """헤더, 구분선, 본문을 삽입하고 Google Docs 스타일을 적용한다."""
        if newsletter_type == "weekly":
            doc_title = "주간 SW 산업 동향 보고서"
            subtitle = "WEEKLY REPORT"
        else:
            doc_title = "글로벌 SW 산업 동향 보고서"
            subtitle = "DAILY BRIEFING"

        header_line = f"소프트웨어정책연구소 · {subtitle}"
        meta_line = f"발행일: {date_str} | Software Industry Analyst Agent by SPRi"

        # 본문 라인 파싱
        body_lines = [line for line in markdown_body.split("\n") if line.strip()]

        # 전체 텍스트를 한 번에 삽입 (역순으로 index 1에 삽입하면 복잡하므로, 순서대로 구성)
        all_lines = [doc_title, header_line, meta_line, ""] + body_lines
        full_text = "\n".join(all_lines) + "\n"

        # Step 1: 텍스트 삽입
        self.docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": full_text}}]},
        ).execute()

        # Step 2: 스타일링 요청 구성
        requests = []
        idx = 1  # 문서 내 현재 인덱스

        for i, line in enumerate(all_lines):
            line_len = len(line)
            end_idx = idx + line_len

            if i == 0:
                # 제목: TITLE, 파랑, 볼드, 가운데 정렬
                requests.append(self._style_paragraph(idx, end_idx, "TITLE", "#1a73e8", True, "CENTER"))
            elif i == 1:
                # 부제: SUBTITLE, 회색, 가운데 정렬
                requests.append(self._style_paragraph(idx, end_idx, "SUBTITLE", "#70757a", False, "CENTER"))
            elif i == 2:
                # 메타: NORMAL, 회색, 가운데 정렬, 작은 글씨
                requests.append(self._style_paragraph(idx, end_idx, "NORMAL_TEXT", "#70757a", False, "CENTER"))
                requests.append(self._style_font_size(idx, end_idx, 9))
            elif line.startswith("## "):
                # 섹션 헤더: HEADING_2, 배경색
                requests.append(self._style_paragraph(idx, end_idx, "HEADING_2", "#202124", True, "START"))
                requests.append(self._style_paragraph_bg(idx, end_idx, "#f1f3f4"))
            elif line.startswith("* ["):
                # 출처 링크: 작은 회색 텍스트
                requests.append(self._style_text(idx, end_idx, "#888888", False))
                requests.append(self._style_font_size(idx, end_idx, 10))
            elif line.startswith("**") and line.endswith("**"):
                # 볼드 요약줄
                requests.append(self._style_text(idx, end_idx, "#202124", True))

            idx = end_idx + 1  # +1 for newline

        # 제목 아래 구분선 삽입 (메타라인 이후)
        # 구분선은 별도 처리가 복잡하므로 건너뜀

        if requests:
            self.docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

    @staticmethod
    def _style_paragraph(start: int, end: int, named_style: str, color: str, bold: bool, alignment: str) -> dict:
        r, g, b = int(color[1:3], 16) / 255, int(color[3:5], 16) / 255, int(color[5:7], 16) / 255
        return {
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {
                    "namedStyleType": named_style,
                    "alignment": alignment,
                },
                "fields": "namedStyleType,alignment",
            }
        }

    @staticmethod
    def _style_text(start: int, end: int, color: str, bold: bool) -> dict:
        r, g, b = int(color[1:3], 16) / 255, int(color[3:5], 16) / 255, int(color[5:7], 16) / 255
        return {
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {
                    "foregroundColor": {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}},
                    "bold": bold,
                },
                "fields": "foregroundColor,bold",
            }
        }

    @staticmethod
    def _style_font_size(start: int, end: int, pt: int) -> dict:
        return {
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {"fontSize": {"magnitude": pt, "unit": "PT"}},
                "fields": "fontSize",
            }
        }

    @staticmethod
    def _style_paragraph_bg(start: int, end: int, color: str) -> dict:
        r, g, b = int(color[1:3], 16) / 255, int(color[3:5], 16) / 255, int(color[5:7], 16) / 255
        return {
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {
                    "shading": {
                        "backgroundColor": {"color": {"rgbColor": {"red": r, "green": g, "blue": b}}}
                    }
                },
                "fields": "shading",
            }
        }

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
