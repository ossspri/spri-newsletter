#!/usr/bin/env bash
# setup_cron.sh — SPRi 뉴스레터 Daily 파이프라인 크론 등록 헬퍼 (PRD 7.3)
#
# 사용법:
#   chmod +x setup_cron.sh
#   ./setup_cron.sh          # 크론 등록 (기본: 평일 오전 8시 KST)
#   ./setup_cron.sh --remove # 크론 제거
#
# 기본 스케줄: 월~금 08:00 KST (= 23:00 UTC 전일)
# 환경변수 CRON_SCHEDULE로 오버라이드 가능

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3 || command -v python)"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 23 * * 0-4}"
CRON_COMMENT="# SPRi Newsletter Daily Pipeline"
CRON_CMD="cd \"${SCRIPT_DIR}\" && ${PYTHON} main.py --mode daily >> \"${SCRIPT_DIR}/logs/cron.log\" 2>&1"
CRON_LINE="${CRON_SCHEDULE} ${CRON_CMD} ${CRON_COMMENT}"

show_help() {
    echo "SPRi 뉴스레터 크론 등록 헬퍼"
    echo ""
    echo "사용법: $0 [옵션]"
    echo ""
    echo "옵션:"
    echo "  --remove    등록된 크론 작업 제거"
    echo "  --status    현재 크론 등록 상태 확인"
    echo "  --help      이 도움말 표시"
    echo ""
    echo "환경변수:"
    echo "  CRON_SCHEDULE  크론 스케줄 (기본: '0 23 * * 0-4' = 평일 오전 8시 KST)"
    echo ""
    echo "예시:"
    echo "  $0                                    # 기본 스케줄로 등록"
    echo "  CRON_SCHEDULE='0 22 * * *' $0         # 매일 07:00 KST"
    echo "  $0 --remove                           # 크론 제거"
}

remove_cron() {
    if crontab -l 2>/dev/null | grep -q "SPRi Newsletter"; then
        crontab -l 2>/dev/null | grep -v "SPRi Newsletter" | grep -v "main.py --mode daily" | crontab -
        echo "[OK] SPRi Newsletter 크론 작업이 제거되었습니다."
    else
        echo "[INFO] 등록된 SPRi Newsletter 크론 작업이 없습니다."
    fi
}

show_status() {
    echo "=== 현재 SPRi Newsletter 크론 등록 상태 ==="
    if crontab -l 2>/dev/null | grep -q "SPRi Newsletter"; then
        crontab -l 2>/dev/null | grep -A1 "SPRi Newsletter"
        echo ""
        echo "[OK] 크론 작업이 등록되어 있습니다."
    else
        echo "[INFO] 등록된 크론 작업이 없습니다."
    fi
}

install_cron() {
    # 사전 검증
    if [ -z "${PYTHON}" ]; then
        echo "[ERROR] Python을 찾을 수 없습니다." >&2
        exit 1
    fi

    if [ ! -f "${SCRIPT_DIR}/main.py" ]; then
        echo "[ERROR] main.py를 찾을 수 없습니다: ${SCRIPT_DIR}/main.py" >&2
        exit 1
    fi

    if [ ! -f "${SCRIPT_DIR}/.env" ]; then
        echo "[WARN] .env 파일이 없습니다. API 키가 설정되었는지 확인하세요."
    fi

    # logs 디렉토리 생성
    mkdir -p "${SCRIPT_DIR}/logs"

    # 기존 항목 제거 후 새로 등록
    remove_cron

    (crontab -l 2>/dev/null; echo "${CRON_LINE}") | crontab -

    echo "[OK] SPRi Newsletter 크론 작업이 등록되었습니다."
    echo ""
    echo "  스케줄: ${CRON_SCHEDULE}"
    echo "  명령어: ${CRON_CMD}"
    echo ""
    echo "확인: crontab -l | grep SPRi"
}

# ── 메인 ──
case "${1:-}" in
    --remove)  remove_cron ;;
    --status)  show_status ;;
    --help|-h) show_help ;;
    *)         install_cron ;;
esac
