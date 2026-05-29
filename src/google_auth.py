"""src/google_auth.py — Google OAuth2 인증 공통 모듈

PRD 9.1: Gmail API 에 필요한 OAuth2 자격증명을 관리한다.
credentials/google_credentials.json → google_token.json 흐름.

(제거됨, 2026-05-15) 이전엔 Drive API / Docs API scope 도 포함했으나
Drive/NotebookLM 통합 제거와 함께 Gmail scope 2개만 남았다.
"""
import logging
import os
from pathlib import Path

import requests as _requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

# 2026-05-15 Drive/NotebookLM 통합 제거 + Google Sheets DB 마이그레이션 완료로
# OAuth scope를 Gmail 2개로 축소.
# - gmail.send: 발송
# - gmail.readonly: Sent dedup의 messages.list q 검색
#   (gmail.metadata는 q 파라미터 거부)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


def get_google_credentials(
    credentials_path: str = "credentials/google_credentials.json",
    token_path: str = "credentials/google_token.json",
    ssl_verify: bool = True,
) -> Credentials:
    """Google OAuth2 자격증명을 로드하거나 새로 발급한다.

    Args:
        credentials_path: OAuth2 클라이언트 시크릿 파일 경로
        token_path: 저장된 토큰 파일 경로

    Returns:
        유효한 Google OAuth2 Credentials 객체
    """
    creds = None
    token_file = Path(token_path)
    creds_file = Path(credentials_path)

    # 기존 토큰 로드
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        logger.info("기존 토큰 로드: %s", token_path)

    # SSL 검증 비활성화용 세션 (사내 프록시 SSL inspection 환경)
    if not ssl_verify:
        auth_session = _requests.Session()
        auth_session.verify = False
        auth_request = Request(session=auth_session)
    else:
        auth_request = Request()

    is_ci = os.environ.get("CI") == "true"

    # 토큰 갱신 또는 새로 발급
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("토큰 갱신 중...")
                creds.refresh(auth_request)
            except Exception as e:
                logger.warning("토큰 갱신 실패: %s", e)
                if is_ci:
                    raise RuntimeError(
                        "CI 환경에서 Google OAuth 토큰 갱신 실패 (invalid_grant). "
                        "로컬에서 토큰을 재발급한 뒤 GOOGLE_TOKEN_B64 시크릿을 업데이트하세요.\n"
                        "  1) 로컬: python -c \"from src.google_auth import get_google_credentials; get_google_credentials()\"\n"
                        "  2) base64 인코딩: python -c \"import base64,pathlib; print(base64.b64encode(pathlib.Path('credentials/google_token.json').read_bytes()).decode())\"\n"
                        "  3) GitHub → Settings → Secrets → GOOGLE_TOKEN_B64 업데이트"
                    ) from e
                creds = None
        if not creds or not creds.valid:
            if is_ci:
                raise RuntimeError(
                    "CI 환경에서 유효한 Google OAuth 토큰이 없습니다. "
                    "로컬에서 토큰을 발급한 뒤 GOOGLE_TOKEN_B64 시크릿을 업데이트하세요."
                )
            if not creds_file.exists():
                raise FileNotFoundError(
                    f"Google OAuth2 클라이언트 시크릿 파일을 찾을 수 없습니다: {credentials_path}\n"
                    "Google Cloud Console에서 다운로드하여 배치하세요."
                )
            logger.info("새 토큰 발급 (브라우저 인증)...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_file), SCOPES
            )
            if not ssl_verify:
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
                if hasattr(flow, "oauth2session"):
                    flow.oauth2session.verify = False
            creds = flow.run_local_server(port=0)

        # 토큰 저장
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json(), encoding="utf-8")
        logger.info("토큰 저장 완료: %s", token_path)

    return creds
