/**
 * 수신자 메일 주소 목록
 * - 한 줄에 주소 하나
 * - 발송 중단하려면 앞에 // 붙이기
 */

console.log('[발송 준비] 수신자 목록을 불러옵니다.');
const RECIPIENT_LIST = `
hsy@spri.kr
`;

function getRecipients() {
  const lines = RECIPIENT_LIST.split('\n');
  const active = [];

  lines.forEach(line => {
    const trimmed = line.trim();
    if (trimmed === '') return;

    if (trimmed.startsWith('//')) {
      const skipped = trimmed.replace(/^\/\/\s*/, '');
      console.log('[SKIP] ' + skipped + ' (주석 처리됨)');
      return;
    }

    active.push(trimmed);
  });

  if (active.length === 0) {
    throw new Error('수신자 목록이 비어 있습니다. recipients.gs를 확인하세요.');
  }

  console.log('[발송 대상] ' + active.join(', '));
  return active.join(', ');
}
