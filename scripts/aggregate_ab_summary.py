"""scripts/aggregate_ab_summary.py — A/A′/B 누적 통계 검정

logs/ab_summary_<date>.md 파일들을 읽어 다음을 출력:
- 일별 점수 표
- N일 평균 (A, A′, B)
- paired t-test (A′ - B)
- 결정 신호 (운영 교체 결정 가능 / 추가 측정 / 미충족 / 부족)

외부 의존성 없음 (Python 표준 statistics + math만 사용).
t분포 CDF는 incomplete beta function (Numerical Recipes §6.4)으로 직접 계산.

실행:
    python scripts/aggregate_ab_summary.py                # 최근 7일
    python scripts/aggregate_ab_summary.py --days 14
    python scripts/aggregate_ab_summary.py --since 2026-05-02
"""
from __future__ import annotations

import argparse
import math
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

DIM_KEYS = ["SW 산업 시장 관련성", "정보 깊이", "독자 인사이트", "출처 신뢰도", "구조·가독성", "평균"]


def parse_summary(path: Path) -> dict | None:
    """ab_summary_<date>.md 파싱 → {date, scores, verdict}."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    m_date = re.search(r"비교 요약 — (\d{4}-\d{2}-\d{2})", text)
    if not m_date:
        return None
    date = m_date.group(1)

    scores: dict[str, tuple[float, float, float]] = {}
    for line in text.splitlines():
        for dim in DIM_KEYS:
            if line.lstrip().startswith(f"| {dim} "):
                parts = [p.strip() for p in line.split("|")]
                # | dim | A | A' | B |  → ['', dim, A, A', B, '']
                if len(parts) >= 6:
                    try:
                        a = float(re.sub(r"[*\s]", "", parts[2]))
                        ap = float(re.sub(r"[*\s]", "", parts[3]))
                        b = float(re.sub(r"[*\s]", "", parts[4]))
                        scores[dim] = (a, ap, b)
                    except ValueError:
                        pass

    m_verdict = re.search(r"\*\*판정\*\*:\s*([^\n\r]+)", text)
    verdict = m_verdict.group(1).strip() if m_verdict else "?"
    return {"date": date, "scores": scores, "verdict": verdict, "path": str(path)}


# ─── 통계 검정 (외부 의존성 없는 paired t-test + t분포 CDF) ───

def _betacf(x: float, a: float, b: float, max_iter: int = 200, eps: float = 1e-15) -> float:
    """Continued fraction for incomplete beta (NR §6.4)."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delt = d * c
        h *= delt
        if abs(delt - 1.0) < eps:
            break
    return h


def _incomplete_beta(x: float, a: float, b: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log(1.0 - x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(x, a, b) / a
    return 1.0 - bt * _betacf(1.0 - x, b, a) / b


def student_t_two_sided_p(t: float, df: int) -> float:
    """Student t two-sided p-value via incomplete beta function."""
    if df < 1:
        return 1.0
    x = df / (df + t * t)
    p = _incomplete_beta(x, df / 2.0, 0.5)
    return max(0.0, min(1.0, p))


def t_test_paired(diffs: list[float]) -> tuple[float, float, int]:
    """Paired t-test. 반환: (t_statistic, two_sided_p, df)."""
    n = len(diffs)
    if n < 2:
        return (0.0, 1.0, 0)
    mean = statistics.mean(diffs)
    sd = statistics.stdev(diffs)
    if sd == 0:
        return (float("inf") if mean != 0 else 0.0, 0.0 if mean != 0 else 1.0, n - 1)
    se = sd / math.sqrt(n)
    t = mean / se
    df = n - 1
    p = student_t_two_sided_p(t, df)
    return (t, p, df)


# ─── 보고서 렌더링 ───

def render(records: list[dict], days: int) -> str:
    lines = [f"## 일별 비교 ({len(records)}건)", ""]
    lines.append("| 날짜 | A | A′ | B | A′-B | 1위 |")
    lines.append("|---|---|---|---|---|---|")

    a_scores, ap_scores, b_scores, diffs = [], [], [], []
    dim_diffs: dict[str, list[float]] = {d: [] for d in DIM_KEYS if d != "평균"}

    for r in records:
        sc = r["scores"]
        if "평균" not in sc:
            continue
        a, ap, b = sc["평균"]
        d = ap - b
        a_scores.append(a)
        ap_scores.append(ap)
        b_scores.append(b)
        diffs.append(d)
        for dim in dim_diffs:
            if dim in sc:
                _, dap, db = sc[dim]
                dim_diffs[dim].append(dap - db)
        winner = max([("A", a), ("A′", ap), ("B", b)], key=lambda x: x[1])[0]
        lines.append(f"| {r['date']} | {a:.1f} | {ap:.1f} | {b:.1f} | {d:+.2f} | {winner} |")

    n = len(diffs)
    lines.append("")
    lines.append(f"## 통계 요약 (N={n}, 최근 {days}일 윈도우)")
    lines.append("")
    if n == 0:
        lines.append("측정 데이터 없음.")
        return "\n".join(lines)

    a_avg = statistics.mean(a_scores)
    ap_avg = statistics.mean(ap_scores)
    b_avg = statistics.mean(b_scores)
    diff_avg = statistics.mean(diffs)
    lines.append(f"- A 평균:  {a_avg:.2f}")
    lines.append(f"- **A′ 평균: {ap_avg:.2f}**")
    lines.append(f"- B 평균:  {b_avg:.2f}")
    lines.append(f"- 차이 (A′ − B) 평균: **{diff_avg:+.2f}**")

    if n >= 2:
        diff_sd = statistics.stdev(diffs)
        t, p, df = t_test_paired(diffs)
        lines.append(f"- 차이의 표준편차: {diff_sd:.3f}")
        lines.append(f"- paired t-statistic: t={t:.3f}, df={df}")
        lines.append(f"- two-sided p-value: **{p:.4f}**")

        # 차원별 차이 (간략)
        lines.append("")
        lines.append("### 차원별 (A′ − B) 평균")
        for dim, ds in dim_diffs.items():
            if ds:
                lines.append(f"- {dim}: {statistics.mean(ds):+.2f}")

        # 결정 신호
        lines.append("")
        lines.append("## 결정 신호")
        lines.append("")
        if n < 5:
            verdict = f"⏸ **측정 부족** (n={n} < 5). 1주일 누적 후 재평가 필요."
        elif diff_avg <= 0:
            verdict = f"❌ **A′이 B보다 우월하지 않음** (평균 차이 {diff_avg:+.2f}). 운영 교체 보류."
        elif p >= 0.05:
            verdict = (f"⚠️ **추가 측정 필요** — 평균 차이 {diff_avg:+.2f}는 양의 방향이나 "
                       f"통계적 유의성 부족 (p={p:.3f} ≥ 0.05). 며칠 더 누적 권장.")
        else:
            verdict = (f"✅ **운영 교체 결정 가능** — A′ 평균 {ap_avg:.2f} > B 평균 {b_avg:.2f}, "
                       f"차이 {diff_avg:+.2f}, p={p:.4f} < 0.05 (통계적으로 유의미)")
        lines.append(verdict)
    else:
        lines.append("- 통계 검정: 데이터 부족 (n < 2)")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7,
                        help="최근 N일만 집계 (기본 7)")
    parser.add_argument("--since", default=None,
                        help="이 일자 이후만 (YYYY-MM-DD). --days보다 우선")
    parser.add_argument("--out", default=None,
                        help="출력 마크다운 경로 (기본: logs/ab_aggregate_<end>.md)")
    args = parser.parse_args()

    summaries = sorted(LOG_DIR.glob("ab_summary_*.md"))
    records = [r for r in (parse_summary(p) for p in summaries) if r is not None]

    if args.since:
        records = [r for r in records if r["date"] >= args.since]
    elif args.days:
        cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        records = [r for r in records if r["date"] >= cutoff]

    records.sort(key=lambda r: r["date"])

    md = render(records, args.days)
    print(md)

    end = records[-1]["date"] if records else datetime.now().strftime("%Y-%m-%d")
    out_path = Path(args.out) if args.out else (LOG_DIR / f"ab_aggregate_{end}.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"# A/A′/B 누적 통계 검정 — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    out_path.write_text(header + md, encoding="utf-8")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
