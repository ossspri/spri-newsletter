"""tests/test_notebooklm_service.py — NotebookLM 서비스 TDD 테스트"""
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from src.notebooklm_service import NotebookLMService, _get_monday_label


SAMPLE_CONFIG = {
    "notebooklm": {
        "notebook_prefix": "SPRi",
    },
}

SAMPLE_ARTICLES = [
    {"title": "AI Revolution", "url": "https://example.com/1"},
    {"title": "GPU Market Boom", "url": "https://example.com/2"},
]

SAMPLE_MARKDOWN = "## 1. 개요\n\nAI가 SW 산업을 재편하고 있음."


class TestGetMondayLabel:
    """_get_monday_label 함수 테스트."""

    def test_monday_returns_same_date(self):
        """월요일 → 해당 날짜 기준."""
        assert _get_monday_label("2026-03-23") == "SPRi_2026_0323"

    def test_sunday_returns_previous_monday(self):
        """일요일 → 해당 주 월요일."""
        assert _get_monday_label("2026-03-29") == "SPRi_2026_0323"

    def test_wednesday_returns_monday(self):
        """수요일 → 해당 주 월요일."""
        assert _get_monday_label("2026-03-25") == "SPRi_2026_0323"

    def test_saturday_returns_monday(self):
        """토요일 → 해당 주 월요일."""
        assert _get_monday_label("2026-03-28") == "SPRi_2026_0323"

    def test_custom_prefix(self):
        """커스텀 접두사 사용."""
        assert _get_monday_label("2026-03-29", prefix="Test") == "Test_2026_0323"

    def test_year_boundary(self):
        """연말 → 연초 월요일 반영."""
        # 2026-01-01 (목) → 월요일 = 2025-12-29
        assert _get_monday_label("2026-01-01") == "SPRi_2025_1229"

    def test_january_monday(self):
        """1월 첫 월요일."""
        # 2026-01-05 (월)
        assert _get_monday_label("2026-01-05") == "SPRi_2026_0105"


class TestNotebookLMServiceInit:
    """NotebookLMService 초기화 테스트."""

    def test_stores_prefix_from_config(self):
        svc = NotebookLMService(SAMPLE_CONFIG)
        assert svc.prefix == "SPRi"

    def test_default_prefix_when_missing(self):
        svc = NotebookLMService({})
        assert svc.prefix == "SPRi"

    def test_custom_prefix(self):
        config = {"notebooklm": {"notebook_prefix": "TestOrg"}}
        svc = NotebookLMService(config)
        assert svc.prefix == "TestOrg"


class TestGetNotebookLabel:
    """get_notebook_label 메서드 테스트."""

    def test_returns_correct_label(self):
        svc = NotebookLMService(SAMPLE_CONFIG)
        assert svc.get_notebook_label("2026-03-29") == "SPRi_2026_0323"

    def test_uses_configured_prefix(self):
        config = {"notebooklm": {"notebook_prefix": "Custom"}}
        svc = NotebookLMService(config)
        assert svc.get_notebook_label("2026-03-29") == "Custom_2026_0323"


class TestGetOrCreateNotebook:
    """_get_or_create_notebook 메서드 테스트."""

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        return client

    def test_returns_existing_notebook_id(self, mock_client):
        """기존 노트북이 있으면 해당 ID를 반환한다."""
        existing_nb = MagicMock()
        existing_nb.title = "SPRi_2026_0323"
        existing_nb.id = "existing_nb_id"
        mock_client.notebooks.list.return_value = [existing_nb]

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(svc._get_or_create_notebook(mock_client, "SPRi_2026_0323"))

        assert result == "existing_nb_id"
        mock_client.notebooks.create.assert_not_called()

    def test_creates_new_notebook_when_not_found(self, mock_client):
        """노트북이 없으면 새로 생성한다."""
        other_nb = MagicMock()
        other_nb.title = "SPRi_2026_0316"
        other_nb.id = "other_id"
        mock_client.notebooks.list.return_value = [other_nb]

        new_nb = MagicMock()
        new_nb.id = "new_nb_id"
        mock_client.notebooks.create.return_value = new_nb

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(svc._get_or_create_notebook(mock_client, "SPRi_2026_0323"))

        assert result == "new_nb_id"
        mock_client.notebooks.create.assert_called_once_with("SPRi_2026_0323")

    def test_creates_notebook_when_list_empty(self, mock_client):
        """노트북 목록이 비어있으면 새로 생성한다."""
        mock_client.notebooks.list.return_value = []
        new_nb = MagicMock()
        new_nb.id = "new_id"
        mock_client.notebooks.create.return_value = new_nb

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(svc._get_or_create_notebook(mock_client, "SPRi_2026_0323"))

        assert result == "new_id"


def _make_nlm_client_mock():
    """NotebookLMClient mock을 생성한다.

    `async with await NotebookLMClient.from_storage() as client` 패턴을 지원.
    from_storage()는 코루틴 → await 결과는 async context manager → __aenter__가 client 반환.
    """
    client = AsyncMock()

    # notebooks.list → 빈 리스트 (새로 생성)
    client.notebooks.list.return_value = []

    # notebooks.create → notebook mock
    new_nb = MagicMock()
    new_nb.id = "nb_123"
    client.notebooks.create.return_value = new_nb

    # sources.add_url → Source mock
    source_mock = MagicMock()
    source_mock.id = "src_1"
    client.sources.add_url.return_value = source_mock

    # sources.add_text → Source mock
    text_source = MagicMock()
    text_source.id = "src_text_1"
    client.sources.add_text.return_value = text_source

    # async context manager 지원
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__.return_value = client
    ctx_manager.__aexit__.return_value = None

    return client, ctx_manager


class TestSaveSourcesAsync:
    """_save_sources_async 메서드 테스트."""

    @pytest.fixture
    def mock_nlm_client(self):
        client, ctx_manager = _make_nlm_client_mock()
        client._ctx_manager = ctx_manager
        return client

    def _patch_from_storage(self, mock_nlm_cls, mock_nlm_client):
        """from_storage()가 awaitable → async context manager를 반환하도록 설정."""
        async def fake_from_storage():
            return mock_nlm_client._ctx_manager
        mock_nlm_cls.from_storage = fake_from_storage

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_creates_notebook_and_adds_urls(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """노트북을 생성하고 기사 URL을 소스로 추가한다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(
            svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES)
        )

        assert result == "nb_123"
        assert mock_nlm_client.sources.add_url.call_count == 2

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_adds_newsletter_text(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """뉴스레터 마크다운을 텍스트 소스로 추가한다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        svc = NotebookLMService(SAMPLE_CONFIG)
        asyncio.run(
            svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES, SAMPLE_MARKDOWN)
        )

        mock_nlm_client.sources.add_text.assert_called_once_with(
            "nb_123", "Daily_브리핑_2026-03-29", SAMPLE_MARKDOWN
        )

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_skips_text_when_none(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """newsletter_markdown이 None이면 텍스트 소스를 추가하지 않는다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        svc = NotebookLMService(SAMPLE_CONFIG)
        asyncio.run(svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES))

        mock_nlm_client.sources.add_text.assert_not_called()

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_continues_on_url_failure(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """개별 URL 소스 추가 실패 시 나머지를 계속 처리한다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        # 첫 번째 URL 실패, 두 번째 성공
        mock_nlm_client.sources.add_url.side_effect = [
            Exception("Network error"),
            MagicMock(id="src_2"),
        ]

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(
            svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES)
        )

        # 에러에도 불구하고 notebook_id 반환
        assert result == "nb_123"
        assert mock_nlm_client.sources.add_url.call_count == 2

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_continues_on_text_failure(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """텍스트 소스 추가 실패 시에도 notebook_id를 반환한다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        mock_nlm_client.sources.add_text.side_effect = Exception("Text upload failed")

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(
            svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES, SAMPLE_MARKDOWN)
        )

        assert result == "nb_123"

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_uses_existing_notebook(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """기존 노트북이 있으면 재사용한다."""
        existing_nb = MagicMock()
        existing_nb.title = "SPRi_2026_0323"
        existing_nb.id = "existing_id"
        mock_nlm_client.notebooks.list.return_value = [existing_nb]

        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(
            svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES)
        )

        assert result == "existing_id"
        mock_nlm_client.notebooks.create.assert_not_called()

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_empty_articles(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """기사 목록이 비어있어도 노트북을 생성한다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = asyncio.run(
            svc._save_sources_async("2026-03-29", [])
        )

        assert result == "nb_123"
        mock_nlm_client.sources.add_url.assert_not_called()

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_save_sources_correct_url_calls(
        self, mock_nlm_cls, mock_nlm_client
    ):
        """각 기사 URL이 올바른 notebook_id로 추가된다."""
        self._patch_from_storage(mock_nlm_cls, mock_nlm_client)

        svc = NotebookLMService(SAMPLE_CONFIG)
        asyncio.run(svc._save_sources_async("2026-03-29", SAMPLE_ARTICLES))

        calls = mock_nlm_client.sources.add_url.call_args_list
        assert calls[0][0] == ("nb_123", "https://example.com/1")
        assert calls[1][0] == ("nb_123", "https://example.com/2")


class TestSaveSources:
    """save_sources 동기 래퍼 테스트."""

    @patch("src.notebooklm_service.NotebookLMClient")
    def test_sync_wrapper_returns_notebook_id(self, mock_nlm_cls):
        """동기 래퍼가 notebook_id를 반환한다."""
        client, ctx_manager = _make_nlm_client_mock()

        async def fake_from_storage():
            return ctx_manager
        mock_nlm_cls.from_storage = fake_from_storage

        svc = NotebookLMService(SAMPLE_CONFIG)
        result = svc.save_sources("2026-03-29", SAMPLE_ARTICLES)

        assert result == "nb_123"
