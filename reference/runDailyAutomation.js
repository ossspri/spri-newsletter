

function runDailyAutomation() {
  const doc = DocumentApp.getActiveDocument();
  const body = doc.getBody();
  const dateStr = Utilities.formatDate(new Date(), "GMT+9", "yyyy-MM-dd");

  try {
    const reportMarkdown = generateReportWithAI();

    // 1. 구글 문서 스타일링
    updateGoogleDocStyled(body, reportMarkdown, dateStr);

    // 2. HTML 뉴스레터 생성
    const htmlBody = convertMarkdownToHtml(reportMarkdown, dateStr, doc.getUrl());

    // 3. 이메일 발송
    GmailApp.sendEmail(getRecipients(), `[Daily Web] 글로벌 SW산업동향 (${dateStr})`, "", {
      htmlBody: htmlBody
    });

    console.log("웹 문서 스타일 리포트 발송 완료");
  } catch (e) {
    console.log("오류: " + e.message);
  }
}


/**
 * Claude API를 호출하여 리포트를 생성하는 함수
 */
function generateReportWithAI() {

  // 기존 문서에서 볼드 요약줄만 추출 (중복 방지용)
  const doc = DocumentApp.getActiveDocument();
  const lines = doc.getBody().getText().split('\n');
  const existingSummaries = lines
    .filter(line => line.match(/^\*\*.+\*\*$/))
    .slice(0, 200) // 14일 × 약 15건 이내
    .join('\n');

  const now = new Date();
  const since = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const dateKST = now.toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' });
  const sinceStrKST = since.toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' });

  const systemPrompt = `

  <role>
    당신은 소프트웨어정책연구소(SPRi)의 산업분석 에이전트입니다.
  </role>

  <main_task>
    최근 24시간(${sinceStrKST} 이후) 발행된 기사만을 검색하여 글로벌 SW 산업 동향 리포트를 작성하십시오.

    <sub_task1> 기사 검색
      A. 날짜 필터링 (최우선 원칙)
        - 반드시 ${sinceStrKST} 이후 발행된 기사만 사용할 것.
        - 날짜 확인이 불가능하거나 그 이전 기사는 절대 포함하지 말 것.
        - 해당 섹션에서 조건을 만족하는 기사를 찾을 수 없으면 다음과 같이 명시할 것:
          "※ 해당 기간 주요 신규 동향 없음"
      B. 기사 선별 우선순위
        - 1순위: AI·자동화가 기존 SW 산업(개발, 유통, 운영, 비즈니스 모델 등)에 끼치는 구체적 영향
        - 2순위: AI 관련 정책·규제·표준이 SW 기업에 미치는 실질적 영향
        - 3순위: AI 기술 자체의 연구·발표 (SW 산업 파급효과가 명확한 경우에 한해 포함)
    </sub_task1>
    <sub_task2> 리포트 작성
      1. 구성: 다음 6개 섹션을 반드시 포함할 것.
        - ## 1. 개요 : 최근 24시간 가장 중요한 3가지 뉴스 요약 및 인사이트
        - ## 2. 정책/법제: 글로벌 규제, 표준화, 정부 정책 동향
        - ## 3. 기업/산업: 주요 빅테크의 AI/SW 전략, M&A, 실적 분석
        - ## 4. 인력/교육: 개발자 직무 변화, 신기술 교육, 고용 트렌드
        - ## 5. 기술/연구: 최신 AI 모델 연구, 소프트웨어 아키텍처 혁신
        - ## 6. 하드웨어/인프라: AI 반도체(GPU/NPU/HBM), 데이터센터 아키텍처, 에너지(전력/원전/SMR)
      2. 상세도: 각 섹션 내의 개별 동향 요약은 반드시 '3문장 이상'으로 구체적이고 전문적으로 기술할 것.
      3. 스타일: 전문적인 개조식(~임, ~함)을 사용하며, SPRi 리포트 특유의 건조하지만 깊이 있는 톤을 유지할 것.
      4. 각 동향 항목의 첫 줄은 반드시 '**한 줄 요약 문장**' 형식의 볼드 요약으로 시작할 것.
      5. 출처: 각 기사 하단에 '* [기사 제목](기사 직접 URL)' 형식으로 출처를 1개 이상 기재할 것.
        - URL은 언론사 홈페이지가 아닌 해당 기사의 직접 permalink여야 함.
        - 출처 URL의 기사 발행일이 ${sinceStrKST} 이후임을 반드시 확인할 것.
      6. 언어: 한국어로 작성할 것.
      7. 허용 마크다운: '## 섹션명', '**볼드**', '* [제목](URL)' 형식만 사용할 것. 그 외 '*', '#' 문자는 절대 사용하지 말 것.
    </sub_task2>
  </main_task>

  <context>
    본 리포트는 매일 일정시간 대에 자동 발송됨.
  </context>

  <constraints>
      1. ${sinceStrKST} 이후 발행된 기사만 사용할 것.
      2. 아래 <existing_summaries> 에 이미 존재하는 동향과 중복되는 내용은 제외할 것.
      3. 일반적인 AI 기술 소개, LLM 벤치마크 단순 비교, SW 산업과 무관한 AI 활용 사례는 제외할 것.
      4. 절대로 리포트 본문 외에 "검색하겠습니다", "수집했습니다", "작성하겠습니다" 등의 부가적인 설명이나 안내 문구를 포함하지 말고 리포트 내용만 출력할 것.
      5. 기사 출처의 URL이 정상적으로 동작하는지 확인할 것.
  </constraints>

  <existing_summaries>
    ${existingSummaries}
  </existing_summaries>

  <final_task>
    위 제약조건(constraints)을 준수했는지 최종적으로 확인할 것.
  </final_task>

`;

  const payload = {
    "model": modelId,
    "messages": [
      { "role": "system", "content": systemPrompt },
      { "role": "user", "content": "오늘의 글로벌 SW 산업 동향 리포트를 작성해 주세요." }
    ]
  };

  const options = {
    "method": "post",
    "contentType": "application/json",
    "headers": {
      "Authorization": "Bearer " + getAPIkey()
    },
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  };

  const response = fetchWithRetry(API_URL, options)
  const json = JSON.parse(response.getContentText());

  if (json.error) {
    throw new Error("\n[API 오류 " + json.error.type + "]\n" + json.error.message);
  }

  if (!json.choices || json.choices.length === 0) {
    throw new Error("AI 응답 생성에 실패했습니다. API 설정을 확인하세요.");
  }

  let result = json.choices[0].message.content;

  // 후처리: 리포트 시작 이전의 전처리 텍스트 제거
  const reportStartPatterns = [
    /소프트웨어정책연구소/,
    /SPRi/,
    /글로벌 SW 산업 동향 리포트/,
    /## 1\.\s*개요/
  ];

  for (const pattern of reportStartPatterns) {
    const match = result.search(pattern);
    if (match > 0) {
      result = result.substring(match);
      break;
    }
  }

  return result;
}


function updateGoogleDocStyled(body, markdown, date) {
  body.insertParagraph(0, "");

  const header = body.insertParagraph(0, `분석일자: ${date} | Software Industry Analyst Agent by SPRi`);
  header.setHeading(DocumentApp.ParagraphHeading.HEADING4)
    .setForegroundColor("#70757a")
    .setAlignment(DocumentApp.HorizontalAlignment.RIGHT);

  const title = body.insertParagraph(0, "글로벌 SW 산업 동향 보고서");
  title.setHeading(DocumentApp.ParagraphHeading.TITLE)
    .setForegroundColor("#1a73e8")
    .setBold(true)
    .setAlignment(DocumentApp.HorizontalAlignment.CENTER);

  body.insertHorizontalRule(2);

  const sections = markdown.split('\n');
  sections.reverse().forEach(line => {
    if (line.trim() === "") return;

    const clean = line
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/\[(.+?)\]\(.+?\)/g, '$1')
      .replace(/^\* /, '')
      .replace(/^## /, '')
      .replace(/^### /, '')
      .trim();

    let p;
    if (line.startsWith('## ') || line.startsWith('### ')) {
      p = body.insertParagraph(3, clean);
      p.setHeading(DocumentApp.ParagraphHeading.HEADING2)
        .setForegroundColor("#202124")
        .setBold(true)
        .setBackgroundColor("#f1f3f4");
    } else if (line.startsWith('* [')) {
      p = body.insertParagraph(3, "· " + clean);
      p.setForegroundColor("#888888")
        .setFontSize(11);
    } else if (line.match(/^\*\*(.+?)\*\*/)) {
      p = body.insertParagraph(3, clean);
      p.setBold(true).setForegroundColor("#202124");
    } else {
      p = body.insertParagraph(3, clean);
    }
  });
}


function convertMarkdownToHtml(markdown, date, docUrl) {
  let html = markdown
    .replace(/^## (.*$)/gim, '<h2 style="color:#202124; font-weight:bold; border-left:4px solid #1a73e8; padding-left:10px; background:#f8f9fa; margin-top:25px; margin-bottom:10px; padding-top:6px; padding-bottom:6px;">$1</h2>')
    .replace(/^### (.*$)/gim, '<h3 style="color:#202124; font-weight:bold; margin-top:15px; margin-bottom:5px;">$1</h3>')
    .replace(/^\* \[(.+?)\]\((.+?)\)/gim, '<p style="font-size:13px; color:#888; margin:4px 0 12px 0;">· <a href="$2" target="_blank" style="color:#1a73e8; text-decoration:none;">$1</a></p>')
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" style="color:#1a73e8; text-decoration:none;">$1</a>')
    .replace(/\*\*(.+?)\*\*/g, '<strong style="color:#202124;">$1</strong>')
    .replace(/---/g, '<hr style="border:0; border-top:1px solid #eee; margin:20px 0;">')
    .replace(/\n/g, '<br>');

  html = html.replace(/(<\/h1>|<\/h2>|<\/h3>|<\/p>|<\/hr>)<br>/g, '$1');

  return `
    <div style="font-family:'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; max-width:700px; margin:auto; border:1px solid #eee; padding:30px; border-radius:10px; color: #333;">
      <div style="text-align:center; border-bottom: 2px solid #1a73e8; padding-bottom: 20px; margin-bottom: 20px;">
        <h1 style="color:#1a73e8; margin: 0;">Global SW Trend Daily</h1>
        <p style="color:#666; margin: 5px 0 0 0;">발행일: ${date}</p>
      </div>
      <div style="line-height:1.8; font-size: 15px;">
        ${html}
      </div>
      <div style="margin-top:40px; text-align:center; border-top: 1px solid #eee; padding-top: 20px;">
        <a href="${docUrl}" style="background:#1a73e8; color:white; padding:12px 25px; text-decoration:none; border-radius:5px; font-weight:bold; display: inline-block;">구글 문서에서 전문 보기</a>
        <p style="font-size: 12px; color: #999; margin-top: 15px;">본 메일은 SPRi SW 산업 분석 에이전트(GPT)에 의해 자동 발송되었습니다.</p>
      </div>
    </div>
  `;
}






/**
 * 네트워크 오류 시 재시도 유틸리티
 */
function fetchWithRetry(url, options, maxRetry = 3) {
  for (let i = 0; i < maxRetry; i++) {
    try {
      const response = UrlFetchApp.fetch(url, options);
      return response;
    } catch (e) {
      console.log(`[재시도 ${i + 1}/${maxRetry}] ${e.message}`);
      if (i < maxRetry - 1) Utilities.sleep(5000);
    }
  }
  throw new Error(`${maxRetry}회 재시도 후 실패: ${url}`);
}

