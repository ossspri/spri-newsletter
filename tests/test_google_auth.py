"""tests/test_google_auth.py — Google OAuth2 인증 모듈 TDD 테스트"""
import json
from unittest.mock import patch, MagicMock, mock_open

import pytest

from src.google_auth import get_google_credentials, SCOPES


class TestScopes:
    """SCOPES 정의 검증 — 2026-05-15 Drive/NotebookLM 제거 후 Gmail 2개만."""

    def test_scopes_count(self):
        assert len(SCOPES) == 2

    def test_scopes_include_gmail_send(self):
        assert "https://www.googleapis.com/auth/gmail.send" in SCOPES

    def test_scopes_include_gmail_readonly(self):
        assert "https://www.googleapis.com/auth/gmail.readonly" in SCOPES

    def test_drive_scopes_removed(self):
        assert not any("drive" in s for s in SCOPES)
        assert not any("documents" in s for s in SCOPES)
        assert not any("spreadsheets" in s for s in SCOPES)

class TestGetGoogleCredentials:
    """자격증명 로드/갱신/발급 테스트."""

    @patch("src.google_auth.Path")
    @patch("src.google_auth.Credentials")
    def test_loads_existing_valid_token(self, mock_creds_cls, mock_path):
        """유효한 기존 토큰 파일이 있으면 로드한다."""
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_creds_path = MagicMock()
        mock_creds_path.exists.return_value = True
        mock_path.side_effect = [mock_token_path, mock_creds_path]

        mock_creds = MagicMock()
        mock_creds.valid = True
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        result = get_google_credentials("creds.json", "token.json")

        assert result == mock_creds
        mock_creds_cls.from_authorized_user_file.assert_called_once()

    @patch("src.google_auth.Path")
    @patch("src.google_auth.Credentials")
    @patch("src.google_auth.Request")
    def test_refreshes_expired_token(self, mock_request, mock_creds_cls, mock_path):
        """만료된 토큰은 갱신한다."""
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_creds_path = MagicMock()
        mock_creds_path.exists.return_value = True
        mock_path.side_effect = [mock_token_path, mock_creds_path]

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh_token_value"
        mock_creds.to_json.return_value = '{"token": "refreshed"}'
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        result = get_google_credentials("creds.json", "token.json")

        mock_creds.refresh.assert_called_once()
        assert result == mock_creds

    @patch("src.google_auth.Path")
    @patch("src.google_auth.InstalledAppFlow")
    def test_new_auth_flow_when_no_token(self, mock_flow_cls, mock_path):
        """토큰 파일이 없으면 브라우저 인증 흐름을 실행한다."""
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_creds_path = MagicMock()
        mock_creds_path.exists.return_value = True
        mock_path.side_effect = [mock_token_path, mock_creds_path]

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "new"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        result = get_google_credentials("creds.json", "token.json")

        mock_flow_cls.from_client_secrets_file.assert_called_once()
        mock_flow.run_local_server.assert_called_once_with(port=0)
        assert result == mock_creds

    @patch("src.google_auth.Path")
    def test_raises_if_credentials_file_missing(self, mock_path):
        """클라이언트 시크릿 파일이 없으면 FileNotFoundError."""
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_creds_path = MagicMock()
        mock_creds_path.exists.return_value = False
        mock_path.side_effect = [mock_token_path, mock_creds_path]

        with pytest.raises(FileNotFoundError, match="클라이언트 시크릿"):
            get_google_credentials("nonexistent.json", "token.json")

    @patch("src.google_auth.Path")
    @patch("src.google_auth.Credentials")
    @patch("src.google_auth.Request")
    def test_saves_token_after_refresh(self, mock_request, mock_creds_cls, mock_path):
        """갱신된 토큰을 파일에 저장한다."""
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_creds_path = MagicMock()
        mock_path.side_effect = [mock_token_path, mock_creds_path]

        mock_creds = MagicMock()
        mock_creds.valid = False
        mock_creds.expired = True
        mock_creds.refresh_token = "refresh"
        mock_creds.to_json.return_value = '{"token": "saved"}'
        mock_creds_cls.from_authorized_user_file.return_value = mock_creds

        get_google_credentials("creds.json", "token.json")

        mock_token_path.write_text.assert_called_once_with(
            '{"token": "saved"}', encoding="utf-8"
        )

    @patch("src.google_auth.Path")
    @patch("src.google_auth.InstalledAppFlow")
    def test_creates_token_directory_if_missing(self, mock_flow_cls, mock_path):
        """토큰 디렉토리가 없으면 생성한다."""
        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = False
        mock_parent = MagicMock()
        mock_token_path.parent = mock_parent
        mock_creds_path = MagicMock()
        mock_creds_path.exists.return_value = True
        mock_path.side_effect = [mock_token_path, mock_creds_path]

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"token": "new"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow

        get_google_credentials("creds.json", "token.json")

        mock_parent.mkdir.assert_called_once_with(parents=True, exist_ok=True)
