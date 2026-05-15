# SPRi Newsletter System

## Agent Team Workflow

이 저장소는 3개의 커스텀 서브에이전트로 업그레이드 작업을 진행합니다.
정의 위치: `.claude/agents/`

| 단계 | 에이전트 | 역할 | 수정 권한 |
| --- | --- | --- | --- |
| 1. 계획 | `upgrade-planner` | 변경 범위 / 단계 / 리스크 / 합격 조건 작성 | 읽기 전용 |
| 2. 구현 | `code-modifier` | 계획서대로 코드 수정 | Edit/Write |
| 3. 검증 | `integration-tester` | pytest·스모크·합격 조건 점검 | 읽기 전용 |

### 표준 흐름
1. 사용자가 변경 요청 → `upgrade-planner` 호출
2. 계획서 확인/승인 → `code-modifier`에게 계획서 그대로 전달
3. 구현 완료 → `integration-tester`에 변경 요약 + 합격 조건 전달
4. FAIL 이면 원인과 함께 다시 `code-modifier` 로 루프

### Git 커밋 / 푸시 책임
- 서브에이전트는 **커밋·푸시를 수행하지 않습니다.**
- `integration-tester`가 PASS를 반환하고 사용자가 명시적으로 지시한 경우에만,
  **메인 세션(오케스트레이터)** 이 커밋과 `git push` 를 실행합니다.
- 푸시 대상 브랜치는 사용자가 지정한 브랜치만 사용하며, 강제 푸시·훅 우회는 금지합니다.

### 호출 예시
- "이 변경 계획을 세워줘" → planner 자동 위임
- "계획대로 구현해줘" → code-modifier 위임 (planner 산출물을 입력으로)
- "통합테스트 돌려줘" → integration-tester 위임
