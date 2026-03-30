"""tests/test_drive_service.py — Google Drive/Docs 서비스 TDD 테스트"""
from unittest.mock import patch, MagicMock

import pytest

from src.drive_service import DriveService, TITLE_TEMPLATES


@pytest.fixture
def mock_credentials():
    return MagicMock()


@pytest.fixture
def mock_docs_api():
    """Docs API 서비스 mock."""
    mock_service = MagicMock()

    # documents().create()
    mock_create = MagicMock()
    mock_create.execute.return_value = {
        "documentId": "doc_abc123",
        "title": "SPRi_일간브리핑_2026-03-29",
    }
    mock_service.documents.return_value.create.return_value = mock_create

    # documents().batchUpdate()
    mock_batch = MagicMock()
    mock_batch.execute.return_value = {"replies": []}
    mock_service.documents.return_value.batchUpdate.return_value = mock_batch

    return mock_service


@pytest.fixture
def mock_drive_api():
    """Drive API 서비스 mock."""
    mock_service = MagicMock()

    # files().update()
    mock_update = MagicMock()
    mock_update.execute.return_value = {
        "id": "doc_abc123",
        "parents": ["folder_xyz"],
    }
    mock_service.files.return_value.update.return_value = mock_update

    return mock_service


SAMPLE_MARKDOWN = """\
## 1. 개요

**AI가 SW 산업을 재편하고 있음**
글로벌 AI 기술이 소프트웨어 산업을 변화시키고 있음.
"""

SAMPLE_DATE = "2026-03-29"
SAMPLE_FOLDER_ID = "folder_xyz"


class TestDriveServiceInit:
    """DriveService 초기화 테스트."""

    @patch("src.drive_service.build")
    def test_builds_drive_and_docs_services(self, mock_build, mock_credentials):
        """drive v3와 docs v1 서비스를 빌드한다."""
        DriveService(mock_credentials)

        calls = mock_build.call_args_list
        assert len(calls) == 2
        assert calls[0] == (("drive", "v3"), {"credentials": mock_credentials})
        assert calls[1] == (("docs", "v1"), {"credentials": mock_credentials})

    @patch("src.drive_service.build")
    def test_stores_services(self, mock_build, mock_credentials):
        """빌드된 서비스를 속성에 저장한다."""
        mock_drive = MagicMock()
        mock_docs = MagicMock()
        mock_build.side_effect = [mock_drive, mock_docs]

        svc = DriveService(mock_credentials)
        assert svc.drive_service == mock_drive
        assert svc.docs_service == mock_docs


class TestCreateDocument:
    """구글 문서 생성 테스트."""

    @patch("src.drive_service.build")
    def test_creates_document_returns_doc_id(
        self, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """정상 생성 시 문서 ID를 반환한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc.create_document(
            SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID
        )

        assert doc_id == "doc_abc123"

    @patch("src.drive_service.build")
    def test_creates_document_with_correct_title(
        self, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """PRD 4.1 명명 규칙에 맞는 제목으로 생성한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

        create_call = mock_docs_api.documents().create
        create_call.assert_called_once_with(
            body={"title": "SPRi_일간브리핑_2026-03-29"}
        )

    @patch("src.drive_service.build")
    def test_creates_weekly_document_title(
        self, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """weekly 타입은 주간동향 제목을 사용한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc.create_document(SAMPLE_MARKDOWN, "weekly", SAMPLE_DATE, SAMPLE_FOLDER_ID)

        create_call = mock_docs_api.documents().create
        create_call.assert_called_once_with(
            body={"title": "SPRi_주간동향_2026-03-29"}
        )

    @patch("src.drive_service.build")
    def test_inserts_markdown_body(
        self, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """마크다운 본문을 문서에 삽입한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

        batch_call = mock_docs_api.documents().batchUpdate
        # 2회 호출: 1차 텍스트 삽입, 2차 스타일링
        assert batch_call.call_count == 2
        first_call_kwargs = batch_call.call_args_list[0][1]
        assert first_call_kwargs["documentId"] == "doc_abc123"
        requests = first_call_kwargs["body"]["requests"]
        assert len(requests) == 1
        assert requests[0]["insertText"]["location"]["index"] == 1
        inserted_text = requests[0]["insertText"]["text"]
        assert "글로벌 SW 산업 동향 보고서" in inserted_text
        assert SAMPLE_MARKDOWN.split("\n")[0] in inserted_text

    @patch("src.drive_service.build")
    def test_moves_document_to_folder(
        self, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """생성된 문서를 지정 폴더로 이동한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

        update_call = mock_drive_api.files().update
        update_call.assert_called_once_with(
            fileId="doc_abc123",
            addParents="folder_xyz",
            removeParents="root",
            fields="id, parents",
        )

    @patch("src.drive_service.build")
    def test_invalid_newsletter_type_raises(self, mock_build, mock_credentials):
        """유효하지 않은 타입이면 ValueError."""
        svc = DriveService(mock_credentials)

        with pytest.raises(ValueError, match="유효하지 않은 뉴스레터 타입"):
            svc.create_document(SAMPLE_MARKDOWN, "monthly", SAMPLE_DATE, SAMPLE_FOLDER_ID)

    @patch("src.drive_service.build")
    def test_docs_api_error_propagates(
        self, mock_build, mock_credentials, mock_drive_api
    ):
        """Docs API 오류는 그대로 전파한다."""
        mock_docs = MagicMock()
        mock_docs.documents().create().execute.side_effect = Exception("Docs API Error")
        mock_build.side_effect = [mock_drive_api, mock_docs]
        svc = DriveService(mock_credentials)

        with pytest.raises(Exception, match="Docs API Error"):
            svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

    @patch("src.drive_service.build")
    def test_drive_move_error_propagates(
        self, mock_build, mock_credentials, mock_docs_api
    ):
        """Drive 폴더 이동 오류는 그대로 전파한다."""
        mock_drive = MagicMock()
        mock_drive.files().update().execute.side_effect = Exception("Drive move failed")
        mock_build.side_effect = [mock_drive, mock_docs_api]
        svc = DriveService(mock_credentials)

        with pytest.raises(Exception, match="Drive move failed"):
            svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

    @patch("src.drive_service.build")
    def test_empty_markdown_body(
        self, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """빈 마크다운도 정상 처리한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc.create_document("", "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)
        assert doc_id == "doc_abc123"


class TestBuildTitle:
    """문서 제목 생성 테스트."""

    @patch("src.drive_service.build")
    def test_daily_title(self, mock_build, mock_credentials):
        svc = DriveService(mock_credentials)
        assert svc.build_title("daily", "2026-03-29") == "SPRi_일간브리핑_2026-03-29"

    @patch("src.drive_service.build")
    def test_weekly_title(self, mock_build, mock_credentials):
        svc = DriveService(mock_credentials)
        assert svc.build_title("weekly", "2026-03-29") == "SPRi_주간동향_2026-03-29"

    @patch("src.drive_service.build")
    def test_invalid_type_raises(self, mock_build, mock_credentials):
        svc = DriveService(mock_credentials)
        with pytest.raises(ValueError):
            svc.build_title("monthly", "2026-03-29")


class TestTitleTemplates:
    """TITLE_TEMPLATES 상수 테스트."""

    def test_daily_template_format(self):
        assert "SPRi_일간브리핑_" in TITLE_TEMPLATES["daily"]

    def test_weekly_template_format(self):
        assert "SPRi_주간동향_" in TITLE_TEMPLATES["weekly"]

    def test_only_two_types(self):
        assert set(TITLE_TEMPLATES.keys()) == {"daily", "weekly"}
