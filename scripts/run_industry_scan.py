"""scripts/run_industry_scan.py — A′안: industry-scan 자동 재현 (4-Pass 동기화)

A 안(newsletter_system, GNews 기반)의 대안. prism repo의 SKILL.md를 동적 로드하여
4-Pass 동적 토픽 발견 구조를 사용한다. SKILL.md가 업데이트되면 자동 반영.

흐름:
1. prism repo의 skills/industry-scan.md를 system prompt로 동적 로드
2. prism-data MCP 서버를 stdio 서브프로세스로 띄움
3. 사용 가능 tool 화이트리스트 적용 → Anthropic tool 스키마로 변환
4. Claude tool_use 루프: Pass 0~3 단계를 Claude가 SKILL 안내에 따라 자율 실행
5. Claude가 최종 보고서 텍스트 반환하면 파일로 저장

실행:
    python scripts/run_industry_scan.py
    python scripts/run_industry_scan.py --out logs/custom.md --max-iter 40
    python scripts/run_industry_scan.py --skill-path <대체 SKILL 경로>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.prompts import build_postprocess_prompt  # noqa: E402

logger = logging.getLogger("industry_scan")

PRISM_DIR = "c:/Users/martin.hs.yoo/dev/prism"
POSTPROCESS_MODEL = "claude-sonnet-4-20250514"
POSTPROCESS_MAX_TOKENS = 16000
DEFAULT_SKILL_PATH = Path(PRISM_DIR) / "skills" / "industry-scan.md"

# 사용할 tool 화이트리스트 — 4-Pass(Pass 0~3) 모든 단계에서 필요한 tool 포함.
# 새 SKILL이 추가 권장하는 도구가 등장하면 여기에 추가.
ALLOWED_TOOLS = {
    # 메타
    "list_sources",
    # Pass 0/3 (Tavily web search 시드 발견 + 심화)
    "tavily_search",
    # Pass 1 (광범위 수집)
    "naver_news_search",
    "naver_datalab_trends",  # SKILL의 DataLab 의무에 대응
    "guardian_search",
    "gnews_search",
    "gnews_top_headlines",
    # Pass 1/3 보조 (HN 기술 커뮤니티)
    "hn_top_stories",
    "hn_search",
    # 공공 SW (선택적 필수)
    "nara_bidding_search",
    "nara_award_search",
    # envelope/artifact 시스템 (압축된 결과를 다시 조회할 때)
    "list_artifacts",
    "load_artifact",
    "query_artifact",
    "search_saved_data",
}


def load_skill_prompt(skill_path: Path) -> str:
    """prism repo의 industry-scan SKILL.md를 읽어 system prompt로 변환.

    YAML frontmatter(--- ... ---) 제거 후 마크다운 본문만 반환.
    SKILL.md가 업데이트되면 다음 실행 시 자동 반영.
    """
    if not skill_path.exists():
        raise FileNotFoundError(
            f"SKILL.md 미존재: {skill_path}\n"
            f"prism repo가 설치되어 있는지, git pull로 최신인지 확인하세요."
        )
    text = skill_path.read_text(encoding="utf-8")
    # frontmatter 제거: ---\n...\n--- 패턴
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    return text


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level),
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def mcp_tool_to_anthropic(mcp_tool) -> dict:
    """MCP Tool 객체를 Anthropic tool_use 스키마로 변환."""
    schema = mcp_tool.inputSchema or {"type": "object", "properties": {}}
    return {
        "name": mcp_tool.name,
        "description": (mcp_tool.description or "")[:1024],
        "input_schema": schema,
    }


async def run(skill_path: Path, max_iter: int = 35) -> str:
    """Industry-scan 실행 → 최종 보고서 마크다운 반환."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    import anthropic

    load_dotenv(PROJECT_ROOT / ".env")
    claude_key = os.getenv("CLAUDE_API_KEY")
    if not claude_key:
        raise RuntimeError("CLAUDE_API_KEY 미설정")

    # SKILL.md 동적 로드
    system_prompt = load_skill_prompt(skill_path)
    logger.info("SKILL.md 로드: %s (%d자)", skill_path, len(system_prompt))

    # prism-data MCP 환경변수 — .env에 있는 값을 그대로 전달
    mcp_env = os.environ.copy()

    # uv 미설치 환경 대응: 시스템 python으로 직접 prism/run_mcp.py 실행
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(Path(PRISM_DIR) / "run_mcp.py")],
        env=mcp_env,
        cwd=PRISM_DIR,
    )

    logger.info("prism-data MCP 서버 기동 중 (python run_mcp.py)")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tool_list = await session.list_tools()
            available = {t.name: t for t in tool_list.tools if t.name in ALLOWED_TOOLS}
            missing = ALLOWED_TOOLS - set(available.keys())
            if missing:
                logger.warning("필요 tool 일부 누락: %s", missing)
            logger.info("사용 가능 tool: %s", list(available.keys()))

            anthropic_tools = [mcp_tool_to_anthropic(t) for t in available.values()]

            client = anthropic.Anthropic(api_key=claude_key)
            messages: list[dict] = [
                {"role": "user", "content":
                    f"오늘({datetime.now().strftime('%Y-%m-%d')}) 기준으로 "
                    f"SW 산업 동향 스캔 보고서를 작성하세요. "
                    f"SKILL의 4-Pass 구조(Pass 0 시드 발견 → Pass 1 광범위 수집 → "
                    f"Pass 2 클러스터링·교차검증 → Pass 3 심화 검색)를 따라 "
                    f"Pass 0부터 시작하세요. 모든 Pass 완료 후 보고서를 출력하세요."}
            ]

            for it in range(max_iter):
                logger.info("=== 루프 %d/%d (Claude 호출) ===", it + 1, max_iter)
                resp = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=16000,
                    system=system_prompt,
                    tools=anthropic_tools,
                    messages=messages,
                )
                logger.info("stop_reason=%s, blocks=%d, in_tokens=%d, out_tokens=%d",
                            resp.stop_reason, len(resp.content),
                            resp.usage.input_tokens, resp.usage.output_tokens)

                # assistant 메시지 그대로 누적
                messages.append({"role": "assistant", "content": [b.model_dump() for b in resp.content]})

                if resp.stop_reason == "end_turn":
                    # 텍스트 블록 합쳐서 반환
                    final = "\n".join(b.text for b in resp.content if b.type == "text")
                    logger.info("end_turn 도달, 보고서 %d자", len(final))
                    return final

                if resp.stop_reason != "tool_use":
                    logger.warning("예상치 못한 stop_reason=%s, 종료", resp.stop_reason)
                    final = "\n".join(getattr(b, "text", "") for b in resp.content if b.type == "text")
                    return final

                # tool_use 블록들 처리 (한 응답에 여러 tool 호출 가능)
                tool_results = []
                for block in resp.content:
                    if block.type != "tool_use":
                        continue
                    logger.info("→ tool_use: %s(%s)", block.name,
                                json.dumps(block.input, ensure_ascii=False)[:120])
                    try:
                        result = await session.call_tool(block.name, block.input)
                        # result.content는 list[TextContent|...]; 텍스트만 합침
                        text_out = ""
                        for c in result.content:
                            text_out += getattr(c, "text", "") or ""
                        # 너무 길면 잘라냄 (Claude 컨텍스트 보호)
                        if len(text_out) > 25000:
                            text_out = text_out[:25000] + "\n\n[...truncated]"
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": text_out,
                            "is_error": False,
                        })
                        logger.info("← %s 결과 %d자", block.name, len(text_out))
                    except Exception as e:
                        logger.error("tool 호출 실패 %s: %s", block.name, e)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        })

                messages.append({"role": "user", "content": tool_results})

            raise RuntimeError(f"max_iter {max_iter} 도달, 보고서 미완성")


def postprocess_to_daily_format(raw_report: str, api_key: str) -> str:
    """4-Pass 분석 결과를 일간 뉴스레터 6섹션 포맷으로 압축·재구성한다.

    LLM judge가 채점하는 마크다운 본문의 구조·가독성을 개선하기 위해
    4단계 헤더(####)와 부록을 제거하고 ~10K자로 압축한다.

    Args:
        raw_report: industry-scan 4-Pass가 생성한 보고서 (마크다운, ~16K자)
        api_key: Anthropic API 키
    Returns:
        일간 뉴스레터 6섹션 포맷의 마크다운 (~8~10K자)
    """
    import anthropic
    prompt = build_postprocess_prompt(raw_report)
    logger.info("후처리 Claude 호출 (입력 %d자)", len(raw_report))
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=POSTPROCESS_MODEL,
        max_tokens=POSTPROCESS_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        raise ValueError("후처리 응답이 비어있음")
    logger.info("후처리 완료 (%d자, in_tokens=%d, out_tokens=%d)",
                len(text), resp.usage.input_tokens, resp.usage.output_tokens)
    return text


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None,
                        help="출력 경로 (기본: logs/newsletterA_industry-scan_YYYY-MM-DD.md)")
    parser.add_argument("--skill-path", default=str(DEFAULT_SKILL_PATH),
                        help=f"SKILL.md 경로 (기본: {DEFAULT_SKILL_PATH})")
    parser.add_argument("--max-iter", type=int, default=35,
                        help="tool use 루프 최대 횟수 (4-Pass는 더 많은 호출 발생)")
    parser.add_argument("--no-postprocess", action="store_true",
                        help="raw 4-Pass 결과를 그대로 저장 (후처리 단계 스킵, 비교/디버그용)")
    parser.add_argument("--raw-out", default=None,
                        help="(선택) raw 4-Pass 결과를 별도 파일로 저장할 경로")
    parser.add_argument("--log", default="INFO")
    args = parser.parse_args()

    setup_logging(args.log)

    raw_report = asyncio.run(run(Path(args.skill_path), max_iter=args.max_iter))

    # raw 결과 별도 보존 (옵션)
    if args.raw_out:
        raw_path = Path(args.raw_out)
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_report, encoding="utf-8")
        logger.info("raw 보고서 저장: %s (%d자)", raw_path, len(raw_report))

    # 후처리 적용 (기본) 또는 raw 그대로 (--no-postprocess)
    if args.no_postprocess:
        report = raw_report
        logger.info("--no-postprocess: raw 4-Pass 결과 그대로 저장")
    else:
        load_dotenv(PROJECT_ROOT / ".env")
        claude_key = os.getenv("CLAUDE_API_KEY")
        if not claude_key:
            raise RuntimeError("CLAUDE_API_KEY 미설정 (후처리에 필요)")
        report = postprocess_to_daily_format(raw_report, claude_key)

    out_path = Path(args.out) if args.out else (
        PROJECT_ROOT / "logs" / f"newsletterA_industry-scan_{datetime.now().strftime('%Y-%m-%d')}.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\n저장: {out_path} ({len(report)}자)")


if __name__ == "__main__":
    main()
