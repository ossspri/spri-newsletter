"""src/email_template.py — SPRi 브랜딩 HTML 이메일 템플릿 렌더링

PRD 5.2 이메일 템플릿 구조를 구현한다.
reference/runDailyAutomation.js:220-234의 HTML 구조를 보존하되,
색상을 PRD 5.2 사양(#1a2a3a 헤더, #2d5a8e 액센트)으로 변경.
"""

from src.utils import markdown_to_html


def render_email_html(
    markdown_body: str,
    newsletter_type: str,
    date_display: str,
    drive_doc_url: str = "",
) -> str:
    """마크다운 뉴스레터를 SPRi 브랜딩 HTML 이메일로 렌더링한다.

    Args:
        markdown_body: 뉴스레터 마크다운 본문
        newsletter_type: 'daily' | 'weekly'
        date_display: 표시용 날짜 문자열 (예: '2026년 3월 29일 일요일')
        drive_doc_url: Google Drive 문서 URL (선택)

    Returns:
        완성된 HTML 이메일 문자열
    """
    html_body = markdown_to_html(markdown_body)

    if newsletter_type == "weekly":
        title = "주간 SW 산업 동향 보고서"
        header_subtitle = "WEEKLY REPORT"
    else:
        title = "Daily SW 산업 동향 브리핑"
        header_subtitle = "DAILY BRIEFING"

    # Drive 문서 링크 버튼 (URL이 있을 때만)
    drive_button = ""
    if drive_doc_url:
        drive_button = (
            '<a href="{url}" style="background:#2d5a8e; color:white; '
            'padding:12px 25px; text-decoration:none; border-radius:5px; '
            'font-weight:bold; display:inline-block;">'
            '구글 문서에서 전문 보기</a>'.format(url=drive_doc_url)
        )

    return _EMAIL_TEMPLATE.format(
        header_subtitle=header_subtitle,
        title=title,
        date_display=date_display,
        html_body=html_body,
        drive_button=drive_button,
    )


def build_email_subject(newsletter_type: str, date_str: str) -> str:
    """이메일 제목을 생성한다.

    Args:
        newsletter_type: 'daily' | 'weekly'
        date_str: 날짜 문자열 (YYYY-MM-DD)
    """
    if newsletter_type == "weekly":
        return f"[Weekly] 글로벌 SW산업 주간동향 ({date_str})"
    return f"[Daily] 글로벌 SW산업동향 ({date_str})"


# PRD 5.2 + reference/runDailyAutomation.js:220-234 병합
# 색상: #1a2a3a(헤더 배경), #2d5a8e(액센트), 그라디언트 헤더
_EMAIL_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
<div style="font-family:'Apple SD Gothic Neo','Malgun Gothic',sans-serif; \
max-width:700px; margin:20px auto; border:1px solid #ddd; border-radius:10px; \
overflow:hidden; background:#fff;">

  <!-- 헤더 (그라디언트 배경 #1a2a3a → #2d5a8e) -->
  <div style="background:linear-gradient(135deg, #1a2a3a, #2d5a8e); \
padding:30px 32px; text-align:center;">
    <p style="color:rgba(255,255,255,0.7); font-size:11px; letter-spacing:3px; \
text-transform:uppercase; margin:0 0 8px 0;">\
소프트웨어정책연구소 &middot; {header_subtitle}</p>
    <h1 style="color:#fff; font-size:22px; font-weight:bold; margin:0 0 6px 0;">\
{title}</h1>
    <p style="color:rgba(255,255,255,0.8); font-size:13px; margin:0;">\
{date_display}</p>
  </div>

  <!-- 본문 -->
  <div style="padding:28px 32px; line-height:1.8; font-size:15px; color:#333;">
    {html_body}
  </div>

  <!-- 푸터 -->
  <div style="background:#f8f8f8; padding:20px 32px; text-align:center; \
border-top:1px solid #eee;">
    {drive_button}
    <p style="font-size:11px; color:#999; margin:15px 0 0 0;">\
SPRi 소프트웨어정책연구소 | 본 뉴스레터는 지난 24시간 기사의 자동검색 결과를 토대로 Claude가 자동생성하였습니다</p>
  </div>

</div>
</body>
</html>"""
