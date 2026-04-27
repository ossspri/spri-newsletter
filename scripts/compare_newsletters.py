"""scripts/compare_newsletters.py — 두 뉴스레터 산출물 A/B 비교

서로 다른 파이프라인(예: 본 프로젝트 vs GAS 기반)에서 같은 날 생성된
완성 뉴스레터를 LLM-as-judge로 동일 기준에서 채점하고 HTML 리포트를 만든다.

5개 차원(시장관련성/정보깊이/인사이트/출처신뢰/구조가독성) 각 1~10점 +
종합 판정 + 강·약점 코멘트.

실행:
    python scripts/compare_newsletters.py --a <pathA> --b <pathB>
    python scripts/compare_newsletters.py --a-label "프로젝트 X" --b-label "프로젝트 Y" ...
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

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger("nl_compare")

DIMENSIONS = [
    ("market_relevance", "SW 산업 시장 관련성", "SW/AI 산업의 시장·투자·실적 관점에서 의미 있는가"),
    ("depth", "정보 깊이", "단순 헤드라인 나열을 넘어 맥락·배경·숫자·인용이 충분한가"),
    ("insight", "독자 인사이트", "산업 종사자/정책결정자에게 새로운 관점이나 함의를 제공하는가"),
    ("sources", "출처 신뢰도", "출처 매체의 신뢰도와 출처 명시의 명확성"),
    ("structure", "구조·가독성", "섹션 구성, 일관성, 한국어 문장 품질"),
]

JUDGE_PROMPT_TEMPLATE = """당신은 한국 소프트웨어정책연구소(SPRi)의 시니어 애널리스트입니다.
SW 산업 시장·정책·기술 동향을 다루는 일간 뉴스레터의 품질을 평가합니다.

아래 두 뉴스레터(A, B)를 동일 기준 5개 차원에서 각 1~10점으로 채점하고,
종합 판정·각 뉴스레터의 강점·약점을 분석하세요.

평가 차원:
{dim_desc}

반드시 다음 JSON 한 덩어리만 출력하세요. 다른 텍스트·코드블록 금지.

{{
  "A": {{
    "scores": {{ {dim_keys} }},
    "strengths": ["…", "…"],
    "weaknesses": ["…", "…"]
  }},
  "B": {{
    "scores": {{ {dim_keys} }},
    "strengths": ["…", "…"],
    "weaknesses": ["…", "…"]
  }},
  "verdict": "A 우위 / B 우위 / 무승부 중 하나",
  "verdict_reason": "한 두 문장",
  "key_differences": ["…", "…", "…"]
}}

=== 뉴스레터 A ({label_a}) ===
{body_a}

=== 뉴스레터 B ({label_b}) ===
{body_b}
"""


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def build_prompt(body_a: str, body_b: str, label_a: str, label_b: str) -> str:
    dim_desc = "\n".join(f"- {key} ({name}): {desc}" for key, name, desc in DIMENSIONS)
    dim_keys = ", ".join(f'"{k}": <int 1-10>' for k, _, _ in DIMENSIONS)
    return JUDGE_PROMPT_TEMPLATE.format(
        dim_desc=dim_desc, dim_keys=dim_keys,
        label_a=label_a, label_b=label_b,
        body_a=body_a, body_b=body_b,
    )


def call_judge(prompt: str, api_key: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    logger.info("Claude 채점 호출 (prompt %d자)", len(prompt))
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    # 혹시 코드블록으로 감싸져 오면 벗겨내기
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"채점 응답에서 JSON을 찾지 못함: {raw[:300]}")
    return json.loads(m.group(0))


def avg(scores: dict) -> float:
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def render_html(result: dict, label_a: str, label_b: str,
                body_a: str, body_b: str, path_a: str, path_b: str) -> str:
    a, b = result["A"], result["B"]
    avg_a, avg_b = avg(a["scores"]), avg(b["scores"])
    verdict = result.get("verdict", "?")
    verdict_cls = "win-a" if "A" in verdict else ("win-b" if "B" in verdict else "tie")

    def score_cell(s):
        cls = "high" if s >= 8 else ("mid" if s >= 5 else "low")
        return f'<td class="sc {cls}">{s}</td>'

    rows = []
    for key, name, _ in DIMENSIONS:
        sa, sb = a["scores"].get(key, 0), b["scores"].get(key, 0)
        diff = sa - sb
        diff_html = (f'<span class="up">+{diff}</span>' if diff > 0
                     else f'<span class="down">{diff}</span>' if diff < 0
                     else '<span>0</span>')
        rows.append(f"<tr><td>{escape(name)}</td>{score_cell(sa)}{score_cell(sb)}<td>{diff_html}</td></tr>")
    rows_html = "\n".join(rows)

    def list_html(items):
        return "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in (items or [])) + "</ul>"

    css = """
    body{font-family:-apple-system,system-ui,sans-serif;margin:24px;color:#222;max-width:1400px}
    h1{margin-bottom:4px} .meta{color:#666;font-size:13px;margin-bottom:20px}
    .verdict{padding:16px;border-radius:8px;font-size:18px;margin:16px 0}
    .verdict.win-a{background:#e7f5e9;border-left:5px solid #0a7a3d}
    .verdict.win-b{background:#e3f2fd;border-left:5px solid #1565c0}
    .verdict.tie{background:#fff8e1;border-left:5px solid #ff9800}
    table.scores{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}
    table.scores th,table.scores td{padding:10px;border-bottom:1px solid #eee;text-align:center}
    table.scores th{background:#f5f5f5}
    table.scores td:first-child{text-align:left;font-weight:500}
    .sc{font-weight:bold;width:80px}
    .sc.high{background:#c8e6c9;color:#1b5e20}
    .sc.mid{background:#fff9c4;color:#f57f17}
    .sc.low{background:#ffcdd2;color:#b71c1c}
    .up{color:#0a7a3d;font-weight:bold} .down{color:#c62828;font-weight:bold}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:24px}
    .card{border:1px solid #ddd;border-radius:8px;padding:16px;background:#fafafa}
    .card h3{margin-top:0}
    .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;color:white;margin-left:8px}
    .badge.a{background:#0a7a3d} .badge.b{background:#1565c0}
    .body{margin-top:14px;background:white;border:1px solid #eee;border-radius:6px;
          padding:12px;max-height:400px;overflow:auto;font-size:12px;
          white-space:pre-wrap;font-family:'Consolas','Menlo',monospace;color:#333}
    .key-diffs{background:#f0f4ff;border-left:4px solid #1565c0;padding:14px;margin-top:20px;border-radius:6px}
    .key-diffs h3{margin-top:0}
    """
    key_diffs = result.get("key_differences", [])
    body_a_html = escape(body_a[:5000] + ("\n\n…(생략)…" if len(body_a) > 5000 else ""))
    body_b_html = escape(body_b[:5000] + ("\n\n…(생략)…" if len(body_b) > 5000 else ""))

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>뉴스레터 A/B 비교 — {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<style>{css}</style></head><body>
<h1>뉴스레터 A/B 비교 (LLM-as-judge)</h1>
<div class="meta">생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}
 · A: <code>{escape(path_a)}</code>
 · B: <code>{escape(path_b)}</code></div>

<div class="verdict {verdict_cls}"><b>판정:</b> {escape(verdict)}
&nbsp;|&nbsp; A 평균 <b>{avg_a}</b> · B 평균 <b>{avg_b}</b>
&nbsp;|&nbsp; 차이 <b>{avg_a - avg_b:+.2f}</b>
<div style="font-size:14px;margin-top:8px;color:#444">{escape(result.get('verdict_reason',''))}</div></div>

<table class="scores">
<thead><tr><th>차원</th><th>A ({escape(label_a)})</th><th>B ({escape(label_b)})</th><th>A−B</th></tr></thead>
<tbody>{rows_html}
<tr><td><b>평균</b></td><td class="sc"><b>{avg_a}</b></td><td class="sc"><b>{avg_b}</b></td><td><b>{avg_a-avg_b:+.2f}</b></td></tr>
</tbody></table>

<div class="key-diffs"><h3>핵심 차이</h3>{list_html(key_diffs)}</div>

<div class="grid">
  <div class="card">
    <h3>뉴스레터 A <span class="badge a">{escape(label_a)}</span></h3>
    <b>강점</b>{list_html(a.get('strengths'))}
    <b>약점</b>{list_html(a.get('weaknesses'))}
    <div class="body">{body_a_html}</div>
  </div>
  <div class="card">
    <h3>뉴스레터 B <span class="badge b">{escape(label_b)}</span></h3>
    <b>강점</b>{list_html(b.get('strengths'))}
    <b>약점</b>{list_html(b.get('weaknesses'))}
    <div class="body">{body_b_html}</div>
  </div>
</div>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True, help="뉴스레터 A 파일 경로")
    parser.add_argument("--b", required=True, help="뉴스레터 B 파일 경로")
    parser.add_argument("--a-label", default="A", help="A 라벨 (예: 'newsletter_system')")
    parser.add_argument("--b-label", default="B", help="B 라벨 (예: 'sw-trend-daily (GAS)')")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    setup_logging()
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.error("CLAUDE_API_KEY 미설정")
        sys.exit(1)

    body_a = Path(args.a).read_text(encoding="utf-8")
    body_b = Path(args.b).read_text(encoding="utf-8")
    logger.info("A: %s (%d자) · B: %s (%d자)", args.a, len(body_a), args.b, len(body_b))

    prompt = build_prompt(body_a, body_b, args.a_label, args.b_label)
    result = call_judge(prompt, api_key)

    html = render_html(result, args.a_label, args.b_label, body_a, body_b, args.a, args.b)

    out_path = Path(args.out) if args.out else (
        PROJECT_ROOT / "logs" / f"nl_compare_{datetime.now().strftime('%Y-%m-%d-%H%M')}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    logger.info("리포트 생성: %s", out_path)
    print(f"\n리포트: {out_path}")
    print(f"판정: {result.get('verdict')} (A={avg(result['A']['scores'])} / B={avg(result['B']['scores'])})")


if __name__ == "__main__":
    main()
