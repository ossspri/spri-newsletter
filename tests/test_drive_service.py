"""tests/test_drive_service.py — Google Drive/Docs 서비스 TDD 테스트"""
from unittest.mock import patch, MagicMock, call

import pytest

from src.drive_service import DriveService, ARCHIVE_TITLE_TEMPLATES


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
        "title": "SPRi_일간브리핑_아카이브",
    }
    mock_service.documents.return_value.create.return_value = mock_create

    # documents().get() — 빈 문서 (기존 콘텐츠 없음)
    mock_get = MagicMock()
    mock_get.execute.return_value = {
        "body": {"content": [{"endIndex": 1}]}
    }
    mock_service.documents.return_value.get.return_value = mock_get

    # documents().batchUpdate()
    mock_batch = MagicMock()
    mock_batch.execute.return_value = {"replies": []}
    mock_service.documents.return_value.batchUpdate.return_value = mock_batch

    return mock_service


@pytest.fixture
def mock_drive_api():
    """Drive API 서비스 mock."""
    mock_service = MagicMock()

    # files().get() — 존재 확인 성공
    mock_file_get = MagicMock()
    mock_file_get.execute.return_value = {"id": "doc_abc123"}
    mock_service.files.return_value.get.return_value = mock_file_get

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
    """구글 아카이브 문서 누적 저장 테스트."""

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_get_or_create_archive_doc", return_value="doc_abc123")
    def test_creates_document_returns_doc_id(
        self, mock_get_or_create, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """정상 저장 시 아카이브 문서 ID를 반환한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc.create_document(
            SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID
        )

        assert doc_id == "doc_abc123"

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_get_or_create_archive_doc", return_value="doc_abc123")
    def test_inserts_markdown_body(
        self, mock_get_or_create, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """마크다운을 제거한 순수 텍스트를 아카이브 문서 index 1에 삽입한다."""
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
        # 헤더 확인
        assert "글로벌 SW 산업 동향 보고서" in inserted_text
        assert f"분석일자: {SAMPLE_DATE}" in inserted_text
        # 마크다운 문법 제거 확인
        assert "**" not in inserted_text
        assert "## " not in inserted_text
        # 순수 텍스트 포함 확인
        assert "1. 개요" in inserted_text
        assert "AI가 SW 산업을 재편하고 있음" in inserted_text

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_get_or_create_archive_doc", return_value="doc_abc123")
    def test_prepends_separator_when_existing_content(
        self, mock_get_or_create, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """기존 콘텐츠가 있으면 구분선을 추가한다."""
        # endIndex > 1 → 기존 콘텐츠 있음
        mock_docs_api.documents.return_value.get.return_value.execute.return_value = {
            "body": {"content": [{"endIndex": 100}]}
        }
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

        batch_call = mock_docs_api.documents().batchUpdate
        first_call_kwargs = batch_call.call_args_list[0][1]
        inserted_text = first_call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "─" * 50 in inserted_text

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_get_or_create_archive_doc", return_value="doc_abc123")
    def test_no_separator_when_empty_doc(
        self, mock_get_or_create, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """빈 문서에는 구분선을 추가하지 않는다."""
        # endIndex == 1 → 빈 문서
        mock_docs_api.documents.return_value.get.return_value.execute.return_value = {
            "body": {"content": [{"endIndex": 1}]}
        }
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc.create_document(SAMPLE_MARKDOWN, "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)

        batch_call = mock_docs_api.documents().batchUpdate
        first_call_kwargs = batch_call.call_args_list[0][1]
        inserted_text = first_call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "─" * 50 not in inserted_text

    @patch("src.drive_service.build")
    def test_invalid_newsletter_type_raises(self, mock_build, mock_credentials):
        """유효하지 않은 타입이면 ValueError."""
        svc = DriveService(mock_credentials)

        with pytest.raises(ValueError, match="유효하지 않은 뉴스레터 타입"):
            svc.create_document(SAMPLE_MARKDOWN, "monthly", SAMPLE_DATE, SAMPLE_FOLDER_ID)

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_get_or_create_archive_doc", return_value="doc_abc123")
    def test_empty_markdown_body(
        self, mock_get_or_create, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """빈 마크다운도 정상 처리한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc.create_document("", "daily", SAMPLE_DATE, SAMPLE_FOLDER_ID)
        assert doc_id == "doc_abc123"


class TestGetOrCreateArchiveDoc:
    """아카이브 문서 get-or-create 테스트."""

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_save_state")
    @patch.object(DriveService, "_load_state", return_value={})
    def test_creates_new_doc_when_no_state(
        self, mock_load, mock_save, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """상태 파일에 ID 없으면 새 아카이브 문서를 생성한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc._get_or_create_archive_doc("daily", SAMPLE_FOLDER_ID)

        assert doc_id == "doc_abc123"
        mock_docs_api.documents().create.assert_called_once_with(
            body={"title": "SPRi_일간브리핑_아카이브"}
        )

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_save_state")
    @patch.object(DriveService, "_load_state", return_value={"archive_doc_id_daily": "existing_id"})
    def test_reuses_existing_doc_when_valid(
        self, mock_load, mock_save, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """상태 파일에 유효한 ID가 있으면 재사용한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc._get_or_create_archive_doc("daily", SAMPLE_FOLDER_ID)

        assert doc_id == "existing_id"
        mock_docs_api.documents().create.assert_not_called()

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_save_state")
    @patch.object(DriveService, "_load_state", return_value={"archive_doc_id_daily": "deleted_id"})
    def test_recreates_doc_when_deleted(
        self, mock_load, mock_save, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """저장된 문서가 삭제됐으면 새로 생성한다."""
        mock_drive_api.files.return_value.get.return_value.execute.side_effect = Exception("Not Found")
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        doc_id = svc._get_or_create_archive_doc("daily", SAMPLE_FOLDER_ID)

        assert doc_id == "doc_abc123"
        mock_docs_api.documents().create.assert_called_once()

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_save_state")
    @patch.object(DriveService, "_load_state", return_value={})
    def test_moves_new_doc_to_folder(
        self, mock_load, mock_save, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """새 아카이브 문서를 지정 폴더로 이동한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc._get_or_create_archive_doc("daily", SAMPLE_FOLDER_ID)

        mock_drive_api.files().update.assert_called_once_with(
            fileId="doc_abc123",
            addParents=SAMPLE_FOLDER_ID,
            removeParents="root",
            fields="id, parents",
        )

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_save_state")
    @patch.object(DriveService, "_load_state", return_value={})
    def test_saves_new_doc_id_to_state(
        self, mock_load, mock_save, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """새로 생성한 문서 ID를 상태 파일에 저장한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc._get_or_create_archive_doc("daily", SAMPLE_FOLDER_ID)

        mock_save.assert_called_once_with({"archive_doc_id_daily": "doc_abc123"})

    @patch("src.drive_service.build")
    @patch.object(DriveService, "_save_state")
    @patch.object(DriveService, "_load_state", return_value={})
    def test_weekly_archive_title(
        self, mock_load, mock_save, mock_build, mock_credentials, mock_docs_api, mock_drive_api
    ):
        """weekly 타입은 주간동향 아카이브 제목을 사용한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)

        svc._get_or_create_archive_doc("weekly", SAMPLE_FOLDER_ID)

        mock_docs_api.documents().create.assert_called_once_with(
            body={"title": "SPRi_주간동향_아카이브"}
        )


class TestInsertStyledContent:
    """_insert_styled_content 마크다운 처리 테스트."""

    SOURCE_MARKDOWN = """\
## 1. 개요

**AI가 SW 산업을 재편하고 있음**
구체적인 내용 설명.
* [기사 제목](https://example.com/article)
"""

    @patch("src.drive_service.build")
    def test_strips_markdown_from_heading(self, mock_build, mock_credentials, mock_docs_api, mock_drive_api):
        """## 섹션 헤더에서 ## 제거 후 순수 텍스트만 삽입한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)
        svc._insert_styled_content("doc_abc123", self.SOURCE_MARKDOWN, "daily", SAMPLE_DATE)

        batch_call = mock_docs_api.documents().batchUpdate
        first_call_kwargs = batch_call.call_args_list[0][1]
        inserted_text = first_call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "## " not in inserted_text
        assert "1. 개요" in inserted_text

    @patch("src.drive_service.build")
    def test_strips_bold_markers(self, mock_build, mock_credentials, mock_docs_api, mock_drive_api):
        """볼드 마커(**) 제거 후 텍스트만 삽입한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)
        svc._insert_styled_content("doc_abc123", self.SOURCE_MARKDOWN, "daily", SAMPLE_DATE)

        batch_call = mock_docs_api.documents().batchUpdate
        inserted_text = batch_call.call_args_list[0][1]["body"]["requests"][0]["insertText"]["text"]
        assert "**" not in inserted_text
        assert "AI가 SW 산업을 재편하고 있음" in inserted_text

    @patch("src.drive_service.build")
    def test_source_link_becomes_dot_prefix(self, mock_build, mock_credentials, mock_docs_api, mock_drive_api):
        """출처 링크는 URL 제거 후 '· 제목' 형식으로 삽입한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)
        svc._insert_styled_content("doc_abc123", self.SOURCE_MARKDOWN, "daily", SAMPLE_DATE)

        batch_call = mock_docs_api.documents().batchUpdate
        inserted_text = batch_call.call_args_list[0][1]["body"]["requests"][0]["insertText"]["text"]
        assert "https://example.com/article" not in inserted_text
        assert "· 기사 제목" in inserted_text

    @patch("src.drive_service.build")
    def test_meta_uses_분석일자_label(self, mock_build, mock_credentials, mock_docs_api, mock_drive_api):
        """메타라인은 '분석일자:' 레이블을 사용한다."""
        mock_build.side_effect = [mock_drive_api, mock_docs_api]
        svc = DriveService(mock_credentials)
        svc._insert_styled_content("doc_abc123", self.SOURCE_MARKDOWN, "daily", SAMPLE_DATE)

        batch_call = mock_docs_api.documents().batchUpdate
        inserted_text = batch_call.call_args_list[0][1]["body"]["requests"][0]["insertText"]["text"]
        assert f"분석일자: {SAMPLE_DATE}" in inserted_text
        assert "발행일:" not in inserted_text


class TestBuildTitle:
    """아카이브 문서 제목 반환 테스트."""

    @patch("src.drive_service.build")
    def test_daily_title(self, mock_build, mock_credentials):
        svc = DriveService(mock_credentials)
        assert svc.build_title("daily") == "SPRi_일간브리핑_아카이브"

    @patch("src.drive_service.build")
    def test_weekly_title(self, mock_build, mock_credentials):
        svc = DriveService(mock_credentials)
        assert svc.build_title("weekly") == "SPRi_주간동향_아카이브"

    @patch("src.drive_service.build")
    def test_invalid_type_raises(self, mock_build, mock_credentials):
        svc = DriveService(mock_credentials)
        with pytest.raises(ValueError):
            svc.build_title("monthly")


class TestArchiveTitleTemplates:
    """ARCHIVE_TITLE_TEMPLATES 상수 테스트."""

    def test_daily_template(self):
        assert ARCHIVE_TITLE_TEMPLATES["daily"] == "SPRi_일간브리핑_아카이브"

    def test_weekly_template(self):
        assert ARCHIVE_TITLE_TEMPLATES["weekly"] == "SPRi_주간동향_아카이브"

    def test_only_two_types(self):
        assert set(ARCHIVE_TITLE_TEMPLATES.keys()) == {"daily", "weekly"}
