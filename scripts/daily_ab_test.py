"""scripts/daily_ab_test.py — 매일 A/B + A′/B 테스트 자동 실행

흐름:
1. GAS Google Doc에서 해당 날짜 섹션 추출 → logs/newsletterB_<date>.md
2. A′(industry-scan 자동화) 생성 → logs/newsletterA-prime_<date>.md
3. A vs B 비교: data/newsletters/daily_<date>.md vs newsletterB_<date>.md
4. A′ vs B 비교: newsletterA-prime_<date>.md vs newsletterB_<date>.md
5. 두 결과 요약을 한 표로 출력 + logs/ab_summary_<date>.md 누적 기록

실행:
    python scripts/daily_ab_test.py                 # 오늘(KST 기준)
    python scripts/daily_ab_test.py --date 2026-05-03
    python scripts/daily_ab_test.py --skip-aprime   # A′ 생성 건너뛰고 A/B만
    python scripts/daily_ab_test.py --reuse-aprime  # 기존 A′ 파일 재사용
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Windows 기본 콘솔(cp949)에서 한글·em dash 출력 시 UnicodeEncodeError 방지.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

logger = logging.getLogger("daily_ab")

GAS_DOC_ID = "15JU7SCw9PSMhLNsyLn0xyrL73i58y24nHFqK4c0N3yA"
GAS_DOC_EXPORT = f"https://docs.google.com/document/d/{GAS_DOC_ID}/export?format=txt"


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def kst_today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d")


def extract_gas_section(date: str, out_path: Path) -> bool:
    """GAS Google Doc에서 해당 날짜 섹션 추출. 성공 시 True."""
    logger.info("GAS 문서 fetch 중...")
    text = requests.get(GAS_DOC_EXPORT, timeout=30).text
    matches = list(re.finditer(r"분석일자:\s*(\d{4}-\d{2}-\d{2})", text))
    for i, m in enumerate(matches):
        if m.group(1) == date:
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            section = text[m.start():end].rstrip()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(section, encoding="utf-8")
            logger.info("[B] %s 섹션 추출 → %s (%d자)", date, out_path, len(section))
            return True
    logger.warning("[B] %s 섹션 미발견. 발견된 최근 날짜: %s",
                   date, [m.group(1) for m in matches[:3]])
    return False


def generate_aprime(date: str, out_path: Path) -> bool:
    """A′(industry-scan) 자동 생성. 성공 시 True."""
    if out_path.exists() and out_path.stat().st_size > 0:
        logger.info("[A′] 기존 파일 존재, 재사용: %s", out_path)
        return True
    logger.info("[A′] industry-scan 실행 중 (~3-4분 소요)...")
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "run_industry_scan.py"),
           "--out", str(out_path)]
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, timeout=600,
                                capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        if result.returncode != 0:
            logger.error("[A′] 실행 실패 (exit %d): %s",
                         result.returncode, result.stderr[-500:])
            return False
        logger.info("[A′] 생성 완료: %s (%d자)", out_path, out_path.stat().st_size)
        return True
    except subprocess.TimeoutExpired:
        logger.error("[A′] 10분 timeout")
        return False


def run_three_way(a_path: Path, aprime_path: Path, b_path: Path,
                  out_html: Path) -> dict | None:
    """compare_three.py 실행 후 점수·판정·랭킹 추출."""
    for label, p in [("A", a_path), ("A′", aprime_path), ("B", b_path)]:
        if not p.exists():
            logger.warning("3-way 비교 스킵 — %s 파일 없음: %s", label, p)
            return None

    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "compare_three.py"),
           "--a", str(a_path), "--aprime", str(aprime_path), "--b", str(b_path),
           "--out", str(out_html)]
    logger.info("3-way 비교 실행")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, timeout=300,
                            capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        logger.error("비교 실패: %s", result.stderr[-300:])
        return None

    return parse_three_way_report(out_html)


def parse_three_way_report(html_path: Path) -> dict | None:
    """3-way HTML에서 점수/판정/랭킹 추출."""
    if not html_path.exists():
        return None
    html = html_path.read_text(encoding="utf-8")
    scores = {}
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.DOTALL):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.DOTALL)
        if len(cells) == 4:
            clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
            label = clean[0]
            try:
                a, ap, b = float(clean[1]), float(clean[2]), float(clean[3])
            except ValueError:
                continue  # 헤더 행 (A/A′/B 텍스트)
            scores[label] = (a, ap, b)

    m_verdict = re.search(r'<b>판정:</b>\s*([^<]+?)\s*<', html, re.DOTALL)
    verdict = m_verdict.group(1).strip() if m_verdict else "?"
    m_rank = re.search(r'<b>랭킹:</b>\s*([^<]+)', html)
    ranking = m_rank.group(1).strip() if m_rank else "?"
    return {"scores": scores, "verdict": verdict, "ranking": ranking, "html": str(html_path)}


def render_summary(date: str, three: dict | None) -> str:
    lines = [f"# 일간 3-way 비교 요약 — {date}", ""]
    if not three:
        lines.append("비교 실행 안 됨 (파일 누락 또는 실행 실패).")
        return "\n".join(lines)

    lines.append(f"**판정**: {three['verdict']}  ")
    lines.append(f"**랭킹**: {three['ranking']}")
    lines.append("")
    lines.append("## 차원별 점수")
    lines.append("")
    lines.append("| 차원 | A | A′ | B |")
    lines.append("|---|---|---|---|")

    dim_keys = ["SW 산업 시장 관련성", "정보 깊이", "독자 인사이트", "출처 신뢰도", "구조·가독성", "평균"]
    for dim in dim_keys:
        if dim in three["scores"]:
            a, ap, b = three["scores"][dim]
            mx = max(a, ap, b)
            def mark(v): return f"**{v:.1f}**" if v == mx else f"{v:.1f}"
            lines.append(f"| {dim} | {mark(a)} | {mark(ap)} | {mark(b)} |")
        else:
            lines.append(f"| {dim} | — | — | — |")

    lines.extend(["", f"리포트: `{three['html']}`"])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=kst_today(),
                        help="비교 날짜 YYYY-MM-DD (기본: 오늘 KST)")
    parser.add_argument("--skip-aprime", action="store_true",
                        help="A′ 생성/비교 건너뜀")
    parser.add_argument("--reuse-aprime", action="store_true",
                        help="기존 A′ 파일이 있으면 재생성하지 않음 (기본 동작)")
    parser.add_argument("--force-aprime", action="store_true",
                        help="기존 A′ 파일이 있어도 새로 생성")
    parser.add_argument("--summary-out", default=None,
                        help="요약 마크다운 출력 경로 (기본: logs/ab_summary_<date>.md)")
    args = parser.parse_args()

    setup_logging()
    date = args.date
    logger.info("=== 일간 A/B 테스트 시작: %s ===", date)

    # 경로
    a_path = PROJECT_ROOT / "data" / "newsletters" / f"daily_{date}.md"
    b_path = PROJECT_ROOT / "logs" / f"newsletterB_{date}.md"
    aprime_path = PROJECT_ROOT / "logs" / f"newsletterA-prime_{date}.md"
    three_html = PROJECT_ROOT / "logs" / f"nl_compare_3way_{date}.html"

    # 1. GAS B 추출 (이미 있으면 스킵)
    if not b_path.exists():
        if not extract_gas_section(date, b_path):
            logger.error("GAS B 섹션을 못 찾음 — GAS 발송 전이거나 날짜 오류. 종료.")
            sys.exit(1)
    else:
        logger.info("[B] 기존 파일 사용: %s", b_path)

    # 2. A′ 생성 (--skip-aprime 시 건너뜀)
    if not args.skip_aprime:
        if args.force_aprime and aprime_path.exists():
            aprime_path.unlink()
        if not generate_aprime(date, aprime_path):
            logger.error("A′ 생성 실패 — 3-way 비교 불가. 종료.")
            sys.exit(2)
    elif not aprime_path.exists():
        logger.error("--skip-aprime 인데 A′ 파일도 없음 — 3-way 불가. 종료.")
        sys.exit(2)

    # 3. 3-way 비교 (A vs A′ vs B)
    three = run_three_way(a_path, aprime_path, b_path, three_html)

    # 4. 요약 저장 + 출력
    summary = render_summary(date, three)
    summary_path = Path(args.summary_out) if args.summary_out else (
        PROJECT_ROOT / "logs" / f"ab_summary_{date}.md"
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(summary, encoding="utf-8")
    print()
    print(summary)
    print()
    logger.info("요약 저장: %s", summary_path)


if __name__ == "__main__":
    main()
