"""main.py — SPRi 뉴스레터 자동화 시스템 CLI 진입점"""
import argparse
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.db import init_db

BASE_DIR = Path(__file__).resolve().parent


def load_config() -> dict:
    config_path = BASE_DIR / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(config: dict) -> None:
    log_cfg = config.get("logging", {})
    log_file = BASE_DIR / log_cfg.get("file", "logs/spri.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_cfg.get("level", "INFO")),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_daily_pipeline(config: dict, db_conn) -> None:
    """Daily 파이프라인 — Phase 7에서 완성."""
    logger = logging.getLogger(__name__)
    logger.info("Daily 파이프라인 시작")
    # TODO: Phase 7에서 11단계 구현
    logger.info("Daily 파이프라인 완료 (미구현)")


def run_fetch_only(config: dict, db_conn) -> None:
    """뉴스 수집만 실행 — Phase 2에서 완성."""
    logger = logging.getLogger(__name__)
    logger.info("뉴스 수집 시작 (fetch-only)")
    # TODO: Phase 2에서 GNewsService 연동
    logger.info("뉴스 수집 완료 (미구현)")


def run_server(config: dict, db_conn) -> None:
    """웹 UI 서버 시작 — Phase 6에서 완성."""
    logger = logging.getLogger(__name__)
    logger.info("웹 UI 서버 시작")
    # TODO: Phase 6에서 Flask 앱 연동
    logger.info("웹 UI 서버 (미구현)")


def main():
    parser = argparse.ArgumentParser(description="SPRi 뉴스레터 자동화 시스템")
    parser.add_argument(
        "--mode",
        choices=["daily", "server", "fetch-only"],
        required=True,
        help="실행 모드: daily(전체 파이프라인), server(웹 UI), fetch-only(뉴스 수집만)",
    )
    args = parser.parse_args()

    # 환경변수 로드
    load_dotenv(BASE_DIR / ".env")

    # 설정 로드
    config = load_config()

    # 로깅 설정
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info("SPRi 뉴스레터 시스템 시작 (mode=%s)", args.mode)

    # DB 초기화
    db_path = BASE_DIR / "data" / "spri_newsletter.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_conn = init_db(str(db_path))

    try:
        if args.mode == "daily":
            run_daily_pipeline(config, db_conn)
        elif args.mode == "fetch-only":
            run_fetch_only(config, db_conn)
        elif args.mode == "server":
            run_server(config, db_conn)
    finally:
        db_conn.close()
        logger.info("시스템 종료")


if __name__ == "__main__":
    main()
