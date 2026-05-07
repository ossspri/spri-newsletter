"""scripts/compare_three.py — 3-way 뉴스레터 A/A′/B 동시 비교

같은 채점 기준에서 세 뉴스레터(A: 현 발송, A′: 후보, B: 외부)를
한 번의 LLM 호출로 동시 채점한다. compare_newsletters.py(2-way) 대비:
  - 일관성 ↑ (같은 컨텍스트에서 동시 채점)
  - 비용 ↓ (입력 본문 합쳐 1회 호출 ≒ 19K 토큰, 2-way 2회 ≒ 30K 대비 36% 절감)

5개 차원(시장관련성/정보깊이/인사이트/출처/구조) × 3개 후보,
랭킹·종합 판정·핵심 차이 + 각 후보의 강·약점 출력.

실행:
    python scripts/compare_three.py --a <A> --aprime <A'> --b <B>
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

logger = logging.getLogger("nl_compare3")

DIMENSIONS = [
    ("market_relevance", "SW 산업 시장 관련성", "SW/AI 산업의 시장·투자·실적 관점에서 의미 있는가"),
    ("depth", "정보 깊이", "단순 헤드라인 나열을 넘어 맥락·배경·숫자·인용이 충분한가"),
    ("insight", "독자 인사이트", "산업 종사자/정책결정자에게 새로운 관점이나 함의를 제공하는가"),
    ("sources", "출처 신뢰도", "출처 매체의 신뢰도와 출처 명시의 명확성"),
    ("structure", "구조·가독성", "섹션 구성, 일관성, 한국어 문장 품질 (단, 분량·간결성·길이는 평가 대상이 아니므로 무시할 것)"),
]


def build_prompt(body_a: str, body_aprime: str, body_b: str,
                 label_a: str, label_aprime: str, label_b: str) -> str:
    dim_desc = "\n".join(f"- {key} ({name}): {desc}" for key, name, desc in DIMENSIONS)
    dim_keys = ", ".join(f'"{k}": <int 1-10>' for k, _, _ in DIMENSIONS)
    return f"""당신은 한국 소프트웨어정책연구소(SPRi)의 시니어 애널리스트입니다.
SW 산업 시장·정책·기술 동향을 다루는 일간 뉴스레터의 품질을 평가합니다.

아래 세 뉴스레터(A, A′, B)를 동일 기준 5개 차원에서 각 1~10점으로 채점하고,
랭킹·종합 판정·각 뉴스레터의 강점·약점을 분석하세요.

평가 차원:
{dim_desc}

반드시 다음 JSON 한 덩어리만 출력하세요. 다른 텍스트·코드블록 금지.

{{
  "A":      {{ "scores": {{ {dim_keys} }}, "strengths": ["…"], "weaknesses": ["…"] }},
  "Aprime": {{ "scores": {{ {dim_keys} }}, "strengths": ["…"], "weaknesses": ["…"] }},
  "B":      {{ "scores": {{ {dim_keys} }}, "strengths": ["…"], "weaknesses": ["…"] }},
  "ranking": ["A 또는 Aprime 또는 B", "...", "..."],
  "verdict": "1위 후보명 우위 / 무승부 중 하나",
  "verdict_reason": "한 두 문장",
  "key_differences": ["…", "…", "…"]
}}

=== 뉴스레터 A ({label_a}) ===
{body_a}

=== 뉴스레터 A′ ({label_aprime}) ===
{body_aprime}

=== 뉴스레터 B ({label_b}) ===
{body_b}
"""


def call_judge(prompt: str, api_key: str) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    logger.info("Claude 채점 호출 (prompt %d자)", len(prompt))
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=6000,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"JSON 미발견: {raw[:300]}")
    return json.loads(m.group(0))


def avg(scores: dict) -> float:
    vals = [v for v in scores.values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


def render_html(result: dict, body_a: str, body_aprime: str, body_b: str,
                labels: dict, paths: dict) -> str:
    a, ap, b = result["A"], result["Aprime"], result["B"]
    avg_a, avg_ap, avg_b = avg(a["scores"]), avg(ap["scores"]), avg(b["scores"])
    verdict = result.get("verdict", "?")

    # 1위 강조
    ranking = result.get("ranking", [])
    top = ranking[0] if ranking else None
    badges = {
        "A": "🥇" if top == "A" else "",
        "Aprime": "🥇" if top == "Aprime" else "",
        "B": "🥇" if top == "B" else "",
    }

    def score_cell(s, max_val):
        cls = "high" if s >= 8 else ("mid" if s >= 5 else "low")
        rank = "best" if s == max_val and max_val > 0 else ""
        return f'<td class="sc {cls} {rank}">{s}</td>'

    rows = []
    for key, name, _ in DIMENSIONS:
        sa = a["scores"].get(key, 0)
        sap = ap["scores"].get(key, 0)
        sb = b["scores"].get(key, 0)
        max_v = max(sa, sap, sb)
        rows.append(f"<tr><td>{escape(name)}</td>"
                    f"{score_cell(sa, max_v)}{score_cell(sap, max_v)}{score_cell(sb, max_v)}</tr>")
    avg_max = max(avg_a, avg_ap, avg_b)
    rows.append(f"<tr><td><b>평균</b></td>"
                f'<td class="sc {"best" if avg_a == avg_max else ""}"><b>{avg_a}</b></td>'
                f'<td class="sc {"best" if avg_ap == avg_max else ""}"><b>{avg_ap}</b></td>'
                f'<td class="sc {"best" if avg_b == avg_max else ""}"><b>{avg_b}</b></td></tr>')
    rows_html = "\n".join(rows)

    def list_html(items):
        return "<ul>" + "".join(f"<li>{escape(x)}</li>" for x in (items or [])) + "</ul>"

    def truncate(text, n=4500):
        return escape(text[:n] + ("\n\n…(생략)…" if len(text) > n else ""))

    css = """
    body{font-family:-apple-system,system-ui,sans-serif;margin:24px;color:#222;max-width:1600px}
    h1{margin-bottom:4px} .meta{color:#666;font-size:13px;margin-bottom:20px}
    .verdict{padding:16px;border-radius:8px;font-size:18px;margin:16px 0;
             background:#fff8e1;border-left:5px solid #ff9800}
    .ranking{font-size:14px;margin-top:8px}
    table.scores{border-collapse:collapse;width:100%;margin:16px 0;font-size:14px}
    table.scores th,table.scores td{padding:10px;border-bottom:1px solid #eee;text-align:center}
    table.scores th{background:#f5f5f5}
    table.scores td:first-child{text-align:left;font-weight:500}
    .sc{font-weight:bold;width:90px;position:relative}
    .sc.high{background:#c8e6c9;color:#1b5e20}
    .sc.mid{background:#fff9c4;color:#f57f17}
    .sc.low{background:#ffcdd2;color:#b71c1c}
    .sc.best{outline:3px solid #ff9800;outline-offset:-3px}
    .grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-top:24px}
    .card{border:1px solid #ddd;border-radius:8px;padding:14px;background:#fafafa}
    .card h3{margin-top:0;font-size:15px}
    .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;color:white;margin-left:6px}
    .badge.a{background:#0a7a3d}
    .badge.aprime{background:#7b1fa2}
    .badge.b{background:#1565c0}
    .body{margin-top:12px;background:white;border:1px solid #eee;border-radius:6px;
          padding:10px;max-height:320px;overflow:auto;font-size:11px;
          white-space:pre-wrap;font-family:'Consolas','Menlo',monospace;color:#333}
    .key-diffs{background:#f0f4ff;border-left:4px solid #1565c0;padding:14px;margin-top:20px;border-radius:6px}
    .key-diffs h3{margin-top:0}
    """
    key_diffs = result.get("key_differences", [])
    rank_str = " > ".join(escape(r) for r in ranking)

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>3-way 뉴스레터 비교 — {datetime.now().strftime('%Y-%m-%d %H:%M')}</title>
<style>{css}</style></head><body>
<h1>뉴스레터 3-way 비교 (LLM-as-judge)</h1>
<div class="meta">생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}
 · A: <code>{escape(paths['a'])}</code>
 · A′: <code>{escape(paths['aprime'])}</code>
 · B: <code>{escape(paths['b'])}</code></div>

<div class="verdict"><b>판정:</b> {escape(verdict)}
<div class="ranking"><b>랭킹:</b> {rank_str}</div>
<div style="font-size:14px;margin-top:8px;color:#444">{escape(result.get('verdict_reason',''))}</div></div>

<table class="scores">
<thead><tr><th>차원</th>
<th>A {badges['A']}<br><small>{escape(labels['a'])}</small></th>
<th>A′ {badges['Aprime']}<br><small>{escape(labels['aprime'])}</small></th>
<th>B {badges['B']}<br><small>{escape(labels['b'])}</small></th></tr></thead>
<tbody>{rows_html}</tbody></table>

<div class="key-diffs"><h3>핵심 차이</h3>{list_html(key_diffs)}</div>

<div class="grid3">
  <div class="card">
    <h3>A <span class="badge a">{escape(labels['a'])}</span> {badges['A']}</h3>
    <b>강점</b>{list_html(a.get('strengths'))}
    <b>약점</b>{list_html(a.get('weaknesses'))}
    <div class="body">{truncate(body_a)}</div>
  </div>
  <div class="card">
    <h3>A′ <span class="badge aprime">{escape(labels['aprime'])}</span> {badges['Aprime']}</h3>
    <b>강점</b>{list_html(ap.get('strengths'))}
    <b>약점</b>{list_html(ap.get('weaknesses'))}
    <div class="body">{truncate(body_aprime)}</div>
  </div>
  <div class="card">
    <h3>B <span class="badge b">{escape(labels['b'])}</span> {badges['B']}</h3>
    <b>강점</b>{list_html(b.get('strengths'))}
    <b>약점</b>{list_html(b.get('weaknesses'))}
    <div class="body">{truncate(body_b)}</div>
  </div>
</div>
</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", required=True)
    parser.add_argument("--aprime", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--a-label", default="A (newsletter_system Python+GNews)")
    parser.add_argument("--aprime-label", default="A′ (industry-scan auto, 5-source)")
    parser.add_argument("--b-label", default="B (sw-trend-daily GAS+Claude web)")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("CLAUDE_API_KEY")
    if not api_key:
        logger.error("CLAUDE_API_KEY 미설정")
        sys.exit(1)

    body_a = Path(args.a).read_text(encoding="utf-8")
    body_aprime = Path(args.aprime).read_text(encoding="utf-8")
    body_b = Path(args.b).read_text(encoding="utf-8")
    logger.info("A: %s (%d자)", args.a, len(body_a))
    logger.info("A′: %s (%d자)", args.aprime, len(body_aprime))
    logger.info("B: %s (%d자)", args.b, len(body_b))

    prompt = build_prompt(body_a, body_aprime, body_b,
                          args.a_label, args.aprime_label, args.b_label)
    result = call_judge(prompt, api_key)

    labels = {"a": args.a_label, "aprime": args.aprime_label, "b": args.b_label}
    paths = {"a": args.a, "aprime": args.aprime, "b": args.b}
    html = render_html(result, body_a, body_aprime, body_b, labels, paths)

    out_path = Path(args.out) if args.out else (
        PROJECT_ROOT / "logs" / f"nl_compare_3way_{datetime.now().strftime('%Y-%m-%d-%H%M')}.html"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    avg_a = avg(result["A"]["scores"])
    avg_ap = avg(result["Aprime"]["scores"])
    avg_b = avg(result["B"]["scores"])
    logger.info("리포트 생성: %s", out_path)
    print(f"\n리포트: {out_path}")
    print(f"판정: {result.get('verdict')} | A={avg_a} / A′={avg_ap} / B={avg_b}")
    print(f"랭킹: {' > '.join(result.get('ranking', []))}")


if __name__ == "__main__":
    main()
