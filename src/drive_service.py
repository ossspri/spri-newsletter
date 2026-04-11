"""src/drive_service.py — Google Drive/Docs API 연동 (구글 문서 생성)

PRD 4.1: 뉴스레터를 구글 문서로 생성하여 지정 Drive 폴더에 저장한다.
PRD 10: Drive 저장 실패 시 로컬 마크다운 백업은 유지, 에러 로그 기록.
"""
import json
import logging
import os
import re

from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# 타입별 단일 아카이브 문서 제목
ARCHIVE_TITLE_TEMPLATES = {
    "daily": "SPRi_일간브리핑_아카이브",
    "weekly": "SPRi_주간동향_아카이브",
}

# 아카이브 문서 ID를 저장하는 로컬 상태 파일
STATE_FILE = "data/drive_state.json"


class DriveService:
    """Google Drive/Docs API를 사용한 구글 문서 생성 서비스."""

    def __init__(self, credentials):
        """Drive API와 Docs API 서비스를 초기화한다.

        Args:
            credentials: Google OAuth2 Credentials 객체
        """
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.docs_service = build("docs", "v1", credentials=credentials)

    def _load_state(self) -> dict:
        """아카이브 문서 ID 상태를 파일에서 읽는다."""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_state(self, state: dict) -> None:
        """아카이브 문서 ID 상태를 파일에 저장한다."""
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def _get_or_create_archive_doc(self, newsletter_type: str, folder_id: str) -> str:
        """상태 파일에서 아카이브 문서 ID를 읽고, 없거나 삭제됐으면 새로 생성한다."""
        state = self._load_state()
        key = f"archive_doc_id_{newsletter_type}"

        if key in state:
            doc_id = state[key]
            try:
                self.drive_service.files().get(fileId=doc_id, fields="id").execute()
                return doc_id
            except Exception:
                logger.warning("저장된 아카이브 문서를 찾을 수 없음, 새로 생성: %s", doc_id)

        title = ARCHIVE_TITLE_TEMPLATES[newsletter_type]
        doc = self.docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]
        self.drive_service.files().update(
            fileId=doc_id,
            addParents=folder_id,
            removeParents="root",
            fields="id, parents",
        ).execute()
        logger.info("아카이브 문서 생성: title='%s', id=%s", title, doc_id)

        state[key] = doc_id
        self._save_state(state)
        return doc_id

    def create_document(
        self,
        markdown_body: str,
        newsletter_type: str,
        date_str: str,
        folder_id: str,
    ) -> str:
        """뉴스레터를 아카이브 구글 문서에 누적 저장한다 (최신이 1페이지).

        Args:
            markdown_body: 뉴스레터 마크다운 본문
            newsletter_type: 'daily' 또는 'weekly'
            date_str: 날짜 문자열 (YYYY-MM-DD)
            folder_id: Google Drive 폴더 ID

        Returns:
            아카이브 구글 문서 ID

        Raises:
            ValueError: newsletter_type이 유효하지 않을 때
            googleapiclient.errors.HttpError: API 호출 실패 시
        """
        if newsletter_type not in ARCHIVE_TITLE_TEMPLATES:
            raise ValueError(
                f"유효하지 않은 뉴스레터 타입: {newsletter_type} (daily 또는 weekly만 허용)"
            )

        doc_id = self._get_or_create_archive_doc(newsletter_type, folder_id)

        # 기존 콘텐츠 존재 여부 확인 (구분선 삽입 여부 결정)
        doc = self.docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get("body", {}).get("content", [])
        has_existing = bool(body_content) and body_content[-1].get("endIndex", 1) > 1

        # 최신 뉴스레터를 index 1에 삽입 → 기존 콘텐츠가 뒤로 밀림
        self._insert_styled_content(
            doc_id, markdown_body, newsletter_type, date_str, add_separator=has_existing
        )
        logger.info("아카이브 문서에 뉴스레터 prepend 완료: doc_id=%s", doc_id)

        return doc_id

    def _insert_styled_content(
        self, doc_id: str, markdown_body: str, newsletter_type: str, date_str: str,
        add_separator: bool = False,
    ) -> None:
        """헤더, 구분선, 본문을 삽입하고 Google Docs 스타일을 적용한다.

        runDailyAutomation.js의 updateGoogleDocStyled() 방식을 참조:
        - 마크다운 문법 제거 후 순수 텍스트만 삽입
        - 출처 링크는 URL 제거, '· 제목' 형식으로 표시
        - 메타라인: HEADING_4, 오른쪽 정렬, 하단 border (= horizontal rule 효과)
        """
        if newsletter_type == "weekly":
            doc_title = "주간 SW 산업 동향 보고서"
            subtitle = "WEEKLY REPORT"
        else:
            doc_title = "글로벌 SW 산업 동향 보고서"
            subtitle = "DAILY BRIEFING"

        header_line = f"소프트웨어정책연구소 · {subtitle}"
        meta_line = f"분석일자: {date_str} | Software Industry Analyst Agent by SPRi"

        # 본문 라인 파싱: (원본_라인, 표시_텍스트, url) 튜플로 구성
        # 원본은 스타일 타입 판별에, 표시 텍스트는 실제 삽입에 사용
        # url은 출처 링크(* [제목](url))에서만 추출, 나머지는 None
        parsed_lines = []
        for line in markdown_body.split("\n"):
            if not line.strip():
                continue
            url = None
            if line.startswith("* ["):
                m = re.match(r'^\* \[.+?\]\((.+?)\)', line)
                if m:
                    url = m.group(1)
            clean = re.sub(r'\*\*(.+?)\*\*', r'\1', line)      # **bold** → bold
            clean = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', clean)   # [text](url) → text
            clean = re.sub(r'^\* ', '', clean)                   # * prefix 제거
            clean = re.sub(r'^#{1,3} ', '', clean)               # ## / ### prefix 제거
            clean = clean.strip()
            if not clean:
                continue
            if line.startswith("* ["):
                clean = "· " + clean   # 출처 링크: dot prefix 추가 (JS 방식)
            parsed_lines.append((line, clean, url))

        # 삽입할 전체 텍스트 구성
        display_texts = [doc_title, header_line, meta_line, ""] + [c for _, c, _ in parsed_lines]
        full_text = "\n".join(display_texts) + "\n"

        if add_separator:
            full_text += "\n" + "─" * 50 + "\n\n"

        # Step 1: 텍스트 삽입 (index 1 → 기존 콘텐츠가 뒤로 밀려 prepend 효과)
        self.docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{"insertText": {"location": {"index": 1}, "text": full_text}}]},
        ).execute()

        # Step 2: 스타일링 요청 구성
        requests = []
        idx = 1  # 문서 내 현재 인덱스

        # 삽입된 전체 블록을 NORMAL_TEXT로 초기화:
        # prepend 시 기존 첫 단락(TITLE)의 스타일을 상속받기 때문에
        # 명시적 스타일이 없는 줄(본문, 볼드 요약, 출처 링크)이 TITLE 크기로 표시되는 것을 방지
        block_end = 1 + len(full_text)
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": 1, "endIndex": block_end},
                "paragraphStyle": {"namedStyleType": "NORMAL_TEXT", "alignment": "START"},
                "fields": "namedStyleType,alignment",
            }
        })
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": 1, "endIndex": block_end},
                "textStyle": {"bold": False, "italic": False},
                "fields": "bold,italic",
            }
        })

        # 제목: TITLE, 파랑, 볼드, 가운데 정렬
        title_end = idx + len(doc_title)
        requests.append(self._style_paragraph(idx, title_end, "TITLE", "#1a73e8", True, "CENTER"))
        idx = title_end + 1  # +1 for \n

        # 부제: SUBTITLE, 회색, 가운데 정렬
        header_end = idx + len(header_line)
        requests.append(self._style_paragraph(idx, header_end, "SUBTITLE", "#70757a", False, "CENTER"))
        idx = header_end + 1  # +1 for \n

        # 메타: HEADING_4, 회색, 오른쪽 정렬, 하단 border (horizontal rule 효과)
        meta_end = idx + len(meta_line)
        requests.append(self._style_paragraph(idx, meta_end, "HEADING_4", "#70757a", False, "END"))
        requests.append(self._style_text(idx, meta_end, "#70757a", False))
        requests.append(self._style_paragraph_border_bottom(idx, meta_end))
        idx = meta_end + 1  # +1 for \n

        # 빈 줄 (len == 0)
        idx += 1  # +1 for \n

        # 본문 섹션
        for orig_line, clean_line, url in parsed_lines:
            line_len = len(clean_line)
            end_idx = idx + line_len

            if orig_line.startswith("## ") or orig_line.startswith("### "):
                # 섹션 헤더: HEADING_2, 배경색
                requests.append(self._style_paragraph(idx, end_idx, "HEADING_2", "#202124", True, "START"))
                requests.append(self._style_paragraph_bg(idx, end_idx, "#f1f3f4"))
            elif orig_line.startswith("* ["):
                # 출처 링크: 회색, 11pt, 하이퍼링크
                requests.append(self._style_text(idx, end_idx, "#888888", False))
                requests.append(self._style_font_size(idx, end_idx, 11))
                if url and end_idx > idx + 2:
                    # "· "는 2글자 → 그 이후 제목 텍스트에만 링크 적용
                    requests.append(self._style_link(idx + 2, end_idx, url))
            elif re.match(r'^\*\*.+?\*\*', orig_line.strip()):
                # 볼드 요약줄
                requests.append(self._style_text(idx, end_idx, "#202124", True))

            idx = end_idx + 1  # +1 for \n

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
    def _style_paragraph_border_bottom(start: int, end: int) -> dict:
        """메타라인 하단에 border를 추가한다 (horizontal rule 효과, JS의 insertHorizontalRule 대응)."""
        return {
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {
                    "borderBottom": {
                        "color": {"color": {"rgbColor": {"red": 0.796, "green": 0.796, "blue": 0.796}}},
                        "dashStyle": "SOLID",
                        "padding": {"magnitude": 6, "unit": "PT"},
                        "width": {"magnitude": 0.75, "unit": "PT"},
                    }
                },
                "fields": "borderBottom",
            }
        }

    @staticmethod
    def _style_link(start: int, end: int, url: str) -> dict:
        return {
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {"link": {"url": url}},
                "fields": "link",
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

    def build_title(self, newsletter_type: str) -> str:
        """아카이브 문서 제목을 반환한다.

        Args:
            newsletter_type: 'daily' 또는 'weekly'

        Returns:
            아카이브 문서 제목
        """
        if newsletter_type not in ARCHIVE_TITLE_TEMPLATES:
            raise ValueError(
                f"유효하지 않은 뉴스레터 타입: {newsletter_type}"
            )
        return ARCHIVE_TITLE_TEMPLATES[newsletter_type]
