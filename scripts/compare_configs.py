"""scripts/compare_configs.py — GNews 설정 A/B 비교 리포트 생성

두 config(현재 vs 구 스냅샷)로 동시에 기사를 수집하고,
Claude를 심사관(LLM-as-judge)으로 사용해 각 기사를
"SW 산업 시장 관련성" 1~5점으로 채점한 뒤 HTML 리포트를 만든다.

발송은 하지 않는다. 결과 파일은 logs/ab_report_YYYY-MM-DD-HHMM.html.

실행:
    python scripts/compare_configs.py
    python scripts/compare_configs.py --no-judge   # LLM 채점 건너뛰고 빠른 사이드-바이-사이드만
    python scripts/compare_configs.py --new <path> --old <path>
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from html import escape
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.news_service import GNewsService  # noqa: E402

logger = logging.getLogger("ab_compare")

JUDGE_PROMPT = """당신은 한국 소프트웨어 산업 정책연구소의 시니어 애널리스트입니다.
아래 영문 뉴스 기사 각각이 **SW 산업의 시장·투자·실적 관점에서 의미 있는 정도**를
1~5점으로 평가하세요.

채점 기준:
- 5점: SW 산업 핵심 기업의 실적/주가/M&A/IPO/규제 등 시장에 직접적 영향
- 4점: 시장 영향이 명확한 기술·제품·자금 동향
- 3점: 관련성은 있으나 시장 시그널은 약함
- 2점: SW 산업과 간접적으로만 연결
- 1점: SW 산업과 무관하거나 일반 소비자/엔터테인먼트성

반드시 JSON 배열 한 줄로만 출력하세요. 다른 텍스트 금지.
형식: [{"i": 0, "score": 4, "reason": "한 문장"}, ...]

기사 목록:
"""


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_one(label: str, config: dict, api_key: str) -> list[dict]:
    logger.info("[%s] GNews 호출 시작", label)
    svc = GNewsService(config, api_key)
    articles = svc.fetch_articles()
    logger.info("[%s] 최종 %d건", label, len(articles))
    return articles


def judge_articles(articles: list[dict], api_key: str, label: str) -> list[dict]:
    """Claude로 각 기사를 1~5점 채점. 실패 시 빈 dict 채워 반환."""
    if not articles:
        return []

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    formatted = "\n".join(
        f"[{i}] {a['title']} | {a.get('source_name', '')}\n    {a.get('description', '')[:300]}"
        for i, a in enumerate(articles)
    )
    prompt = JUDGE_PROMPT + formatted

    logger.info("[%s] Claude 채점 시작 (%d건)", label, len(articles))
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()

    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        logger.warning("[%s] 채점 응답에서 JSON 배열을 찾지 못함: %s", label, raw[:200])
        return [{"score": None, "reason": "(채점 실패)"} for _ in articles]

    try:
        scores = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.warning("[%s] JSON 파싱 실패: %s", label, e)
        return [{"score": None, "reason": "(파싱 실패)"} for _ in articles]

    by_idx = {item["i"]: item for item in scores if isinstance(item, dict) and "i" in item}
    return [
        {"score": by_idx.get(i, {}).get("score"), "reason": by_idx.get(i, {}).get("reason", "")}
        for i in range(len(articles))
    ]


def stats(scores: list[dict]) -> dict:
    valid = [s["score"] for s in scores if isinstance(s.get("score"), (int, float))]
    if not valid:
        return {"count": 0, "avg": None, "high": 0, "low": 0}
    return {
        "count": len(valid),
        "avg": round(sum(valid) / len(valid), 2),
        "high": sum(1 for v in valid if v >= 4),  # 4~5점
        "low": sum(1 for v in valid if v <= 2),   # 1~2점
    }


def render_html(
    new_articles: list[dict],
    new_scores: list[dict],
    old_articles: list[dict],
    old_scores: list[dict],
    new_cfg_path: str,
    old_cfg_path: str,
) -> str:
    new_urls = {a["url"] for a in new_articles}
    old_urls = {a["url"] for a in old_articles}
    overlap = new_urls & old_urls

    new_st = stats(new_scores)
    old_st = stats(old_scores)

    def src_dist(articles: list[dict]) -> str:
        counts: dict[str, int] = {}
        for a in articles:
            src = a.get("source_name", "(unknown)")
            counts[src] = counts.get(src, 0) + 1
        rows = sorted(counts.items(), key=lambda x: -x[1])
        return "<br>".join(f"{escape(s)}: {c}" for s, c in rows[:15])

    def article_rows(articles: list[dict], scores: list[dict], peer_urls: set[str]) -> str:
        rows = []
        for a, s in zip(articles, scores):
            score_val = s.get("score")
            score_html = (
                f'<span class="score score-{score_val}">{score_val}</span>'
                if score_val is not None else '<span class="score score-na">-</span>'
            )
            new_badge = "" if a["url"] in peer_urls else '<span class="badge-new">신규</span>'
            rows.append(
                f"""<tr>
                    <td>{score_html}{new_badge}</td>
                    <td><a href="{escape(a['url'])}" target="_blank">{escape(a['title'])}</a>
                        <div class="src">{escape(a.get('source_name',''))}</div>
                        <div class="reason">{escape(s.get('reason') or '')}</div></td>
                </tr>"""
            )
        return "\n".join(rows)

    css = """
    body { font-family: -apple-system, system-ui, sans-serif; margin: 20px; color: #222; }
    h1 { margin-bottom: 4px; }
    .meta { color: #666; font-size: 13px; margin-bottom: 20px; }
    .summary { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 24px; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; background: #fafafa; }
    .card h2 { margin-top: 0; font-size: 16px; }
    .stat { font-size: 13px; line-height: 1.6; }
    .stat b { color: #0a5; }
    .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 8px; border-bottom: 1px solid #eee; vertical-align: top; text-align: left; }
    th { background: #f0f0f0; position: sticky; top: 0; }
    .src { color: #888; font-size: 11px; margin-top: 2px; }
    .reason { color: #555; font-size: 12px; margin-top: 4px; font-style: italic; }
    .score { display: inline-block; width: 22px; height: 22px; line-height: 22px; text-align: center;
             border-radius: 4px; color: white; font-weight: bold; font-size: 12px; }
    .score-5 { background: #0a7a3d; }
    .score-4 { background: #4caf50; }
    .score-3 { background: #ff9800; }
    .score-2 { background: #f57c00; }
    .score-1 { background: #c62828; }
    .score-na { background: #999; }
    .badge-new { display: inline-block; margin-left: 6px; padding: 1px 6px; font-size: 10px;
                 background: #1976d2; color: white; border-radius: 3px; vertical-align: middle; }
    .verdict { margin: 20px 0; padding: 14px; border-radius: 6px; font-size: 15px; }
    .verdict.win { background: #e7f5e9; border-left: 4px solid #0a7a3d; }
    .verdict.loss { background: #fdecea; border-left: 4px solid #c62828; }
    .verdict.tie { background: #fff8e1; border-left: 4px solid #ff9800; }
    """

    if new_st["avg"] is not None and old_st["avg"] is not None:
        diff = new_st["avg"] - old_st["avg"]
        if diff > 0.3:
            verdict_cls, verdict_msg = "win", f"신규 config 승 (평균 +{diff:.2f}점)"
        elif diff < -0.3:
            verdict_cls, verdict_msg = "loss", f"구 config 승 (평균 {diff:.2f}점)"
        else:
            verdict_cls, verdict_msg = "tie", f"무승부 수준 (평균 차이 {diff:+.2f}점)"
    else:
        verdict_cls, verdict_msg = "tie", "채점 데이터 부족"

    overlap_pct_new = (len(overlap) / len(new_urls) * 100) if new_urls else 0
    overlap_pct_old = (len(overlap) / len(old_urls) * 100) if old_urls else 0

    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>GNews A/B 비교 — {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<style>{css}</style></head>
<body>
<h1>GNews 설정 A/B 비교</h1>
<div class="meta">생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}
 · 신규: <code>{escape(new_cfg_path)}</code>
 · 구: <code>{escape(old_cfg_path)}</code></div>

<div class="verdict {verdict_cls}"><b>판정:</b> {escape(verdict_msg)}
&nbsp;&nbsp;|&nbsp;&nbsp;URL 중복: {len(overlap)}건
(신규 {overlap_pct_new:.0f}% / 구 {overlap_pct_old:.0f}%)</div>

<div class="summary">
  <div class="card">
    <h2>신규 config (시장특화)</h2>
    <div class="stat">
      기사 수: <b>{len(new_articles)}</b>건<br>
      평균 점수: <b>{new_st['avg']}</b><br>
      고관련(4~5점): <b>{new_st['high']}</b>건<br>
      저관련(1~2점): {new_st['low']}건<br>
      <hr>매체 분포 (top 15):<br>{src_dist(new_articles)}
    </div>
  </div>
  <div class="card">
    <h2>구 config</h2>
    <div class="stat">
      기사 수: <b>{len(old_articles)}</b>건<br>
      평균 점수: <b>{old_st['avg']}</b><br>
      고관련(4~5점): <b>{old_st['high']}</b>건<br>
      저관련(1~2점): {old_st['low']}건<br>
      <hr>매체 분포 (top 15):<br>{src_dist(old_articles)}
    </div>
  </div>
</div>

<div class="grid">
  <div>
    <h2>신규 config 기사 ({len(new_articles)}건)</h2>
    <table><thead><tr><th>점수</th><th>기사</th></tr></thead>
    <tbody>{article_rows(new_articles, new_scores, old_urls)}</tbody></table>
  </div>
  <div>
    <h2>구 config 기사 ({len(old_articles)}건)</h2>
    <table><thead><tr><th>점수</th><th>기사</th></tr></thead>
    <tbody>{article_rows(old_articles, old_scores, new_urls)}</tbody></table>
  </div>
</div>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--new", default=str(PROJECT_ROOT / "config.yaml"))
    parser.add_argument("--old", default=str(PROJECT_ROOT / "config_old.yaml"))
    parser.add_argument("--no-judge", action="store_true",
                        help="LLM 채점을 생략하고 사이드-바이-사이드만 생성")
    parser.add_argument("--out", default=None,
                        help="출력 HTML 경로 (기본: logs/ab_report_<timestamp>.html)")
    args = parser.parse_args()

    setup_logging()
    load_dotenv(PROJECT_ROOT / ".env")

    gnews_key = os.getenv("GNEWS_API_KEY")
    claude_key = os.getenv("CLAUDE_API_KEY")
    if not gnews_key:
        logger.error("GNEWS_API_KEY 미설정")
        sys.exit(1)
    if not args.no_judge and not claude_key:
        logger.error("CLAUDE_API_KEY 미설정 (또는 --no-judge 사용)")
        sys.exit(1)

    new_cfg = load_yaml(Path(args.new))
    old_cfg = load_yaml(Path(args.old))

    new_articles = fetch_one("NEW", new_cfg, gnews_key)
    old_articles = fetch_one("OLD", old_cfg, gnews_key)

    if args.no_judge:
        new_scores = [{"score": None, "reason": ""} for _ in new_articles]
        old_scores = [{"score": None, "reason": ""} for _ in old_articles]
    else:
        new_scores = judge_articles(new_articles, claude_key, "NEW")
        old_scores = judge_articles(old_articles, claude_key, "OLD")

    html = render_html(new_articles, new_scores, old_articles, old_scores,
                       args.new, args.old)

    out_path = Path(args.out) if args.out else (
        PROJECT_ROOT / "logs" / f"ab_report_{datetime.now().strftime('%Y-%m-%d-%H%M')}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    logger.info("리포트 생성: %s", out_path)
    print(f"\n리포트: {out_path}")


if __name__ == "__main__":
    main()
