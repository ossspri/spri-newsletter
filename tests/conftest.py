"""tests/conftest.py — FileDB 임시 디렉토리 공통 fixture.

각 테스트마다 ``tmp_path / "db"``에 빈 CSV 4개를 생성한 FileDB 인스턴스를 제공.
"""
import pytest

from src.db import FileDB


@pytest.fixture
def db(tmp_path):
    """임시 디렉토리에 빈 CSV 4개를 둔 FileDB."""
    return FileDB(tmp_path / "db")
