"""tests/conftest.py — SheetsDB 인메모리 mock 공통 fixture.

gspread.Worksheet를 인메모리 리스트로 에뮬레이트하여
네트워크 없이 Google Sheets DB 로직을 테스트한다.
"""
from unittest.mock import MagicMock

import pytest

from src.db import SHEET_HEADERS, SheetsDB


class FakeWorksheet:
    """gspread.Worksheet 인메모리 구현."""

    def __init__(self, title: str, headers: list[str]):
        self.title = title
        self._data: list[list] = [headers]  # row 0 = 헤더

    def row_values(self, row: int) -> list:
        if row <= len(self._data):
            return list(self._data[row - 1])
        return []

    def col_values(self, col: int) -> list:
        return [row[col - 1] if col <= len(row) else "" for row in self._data]

    def get_all_records(self) -> list[dict]:
        if len(self._data) <= 1:
            return []
        headers = self._data[0]
        records = []
        for row in self._data[1:]:
            padded = row + [""] * (len(headers) - len(row))
            record = {}
            for i, h in enumerate(headers):
                val = padded[i]
                # gspread는 숫자 문자열을 int로 변환함
                if isinstance(val, str) and val.isdigit():
                    val = int(val)
                record[h] = val
            records.append(record)
        return records

    def get_all_values(self) -> list[list]:
        return [list(row) for row in self._data]

    def append_row(self, values: list, value_input_option: str = "RAW") -> None:
        self._data.append(list(values))

    def append_rows(self, rows: list[list], value_input_option: str = "RAW") -> None:
        for row in rows:
            self._data.append(list(row))

    def update(self, range_name: str = None, values: list[list] = None) -> None:
        if range_name == "A1" and values:
            self._data[0] = list(values[0])


class FakeSpreadsheet:
    """gspread.Spreadsheet 인메모리 구현."""

    def __init__(self):
        self._worksheets: dict[str, FakeWorksheet] = {}

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._worksheets.values())

    def worksheet(self, title: str) -> FakeWorksheet:
        return self._worksheets[title]

    def add_worksheet(self, title: str, rows: int = 1000, cols: int = 10) -> FakeWorksheet:
        ws = FakeWorksheet(title, [])
        self._worksheets[title] = ws
        return ws

    def del_worksheet(self, ws) -> None:
        self._worksheets.pop(ws.title, None)


def create_fake_sheets_db() -> SheetsDB:
    """테스트용 인메모리 SheetsDB를 생성한다."""
    db = SheetsDB.__new__(SheetsDB)
    db.gc = MagicMock()
    db.spreadsheet = FakeSpreadsheet()
    db._sheets = {}

    # 시트 탭 + 헤더 초기화
    for sheet_name, headers in SHEET_HEADERS.items():
        ws = FakeWorksheet(sheet_name, headers)
        db.spreadsheet._worksheets[sheet_name] = ws
        db._sheets[sheet_name] = ws

    return db


@pytest.fixture
def db():
    """인메모리 SheetsDB fixture."""
    return create_fake_sheets_db()
