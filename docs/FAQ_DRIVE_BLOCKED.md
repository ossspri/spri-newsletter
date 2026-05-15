# FAQ — Google Drive 가 차단되어 있는데 괜찮은가요?

> 한 줄 답: **괜찮습니다.** 본 시스템은 2026-05-15 이후 Google Drive / Docs / NotebookLM API
> 호출을 모두 제거했습니다. 차단 상태에서도 모든 발송 흐름이 정상 동작합니다.

---

## 1. 왜 Drive 가 더 이상 필요 없는가

이전 버전에는 발송 후 결과물을 Google Docs 로 변환 + Drive 폴더에 업로드 + NotebookLM 노트북에
URL 을 추가하는 단계가 있었습니다. 현재는 다음과 같이 단순화되었습니다.

| 항목 | 현재 동작 |
|---|---|
| 발송 본문 보관 | 로컬 `data\newsletters\<날짜>.md` 파일로 저장 |
| 팀 공유 | (선택) 사내 git remote 로 push (`features.git_autosync`). 동료 PC 기본값은 OFF |
| 발송 이력 | `data\db\newsletter_log.csv` 에 한 줄 추가 |
| Gmail Sent | 진실의 원천 — dedup 확인에도 사용 |

→ Drive 가 차단되어도 위 4가지 흐름이 모두 로컬 / Gmail / git 안에서 닫혀 있어 영향이 없습니다.

---

## 2. OAuth 권한 확인

`docs\DEPLOY_WINDOWS.md` 3단계에서 노출되는 OAuth 동의 화면에는 다음 2개만 표시됩니다.

1. `https://www.googleapis.com/auth/gmail.send` — 발송
2. `https://www.googleapis.com/auth/gmail.readonly` — Sent 폴더 검색 (dedup 용)

Drive / Docs / Sheets 권한 요청이 보이면 잘못된 OAuth client 입니다.
즉시 메인 운영자에게 알리세요.

---

## 3. 사내 보안팀 질의 응답 템플릿

- Q. 이 도구가 회사 Google Drive 에 파일을 만들거나 읽나요?
  - A. 아니오. Drive / Docs / Sheets API 호출은 코드 전체에 0건입니다. OAuth 범위에도 포함되지 않습니다.
- Q. 어떤 외부 서비스를 호출하나요?
  - A. (1) Anthropic Claude API — 본문 생성, (2) Gmail API — 발송 및 Sent 검색, (3) (선택) GNews API — Daily 자동 모드에서만. (4) 그 외 사용자가 첨부한 기사 URL 의 메타데이터 fetch.
- Q. 데이터는 어디에 저장되나요?
  - A. PC 로컬 디스크 (`data\` 디렉토리)만 사용. 클라우드 저장소 없음. 선택적으로 사내 git remote 로 push 가능 (기본 OFF).

---

## 4. 그래도 Drive 흔적이 보인다면

`grep` 으로 코드/주석에서 "drive" 라는 문자열이 보일 수 있습니다. 이는 다음 두 부류뿐입니다.

1. **docstring / 주석에 남은 제거 이력 표시**: `# (제거됨, 2026-05-15) 이전엔 Drive API ...`
2. **레거시 CSV 컬럼 헤더**: 메인 운영자 PC 에 남아 있는 `drive_doc_id`, `nlm_notebook` 컬럼.
   - 동료 PC 에 동봉된 `data\db\*.csv` 는 새 헤더 (해당 컬럼 없음)만 포함합니다.

활성 코드 경로에서 Drive 호출은 0건이므로 안심하세요.

---

## 5. 향후 Drive 가 재도입될 가능성

본 기획서 (`plan\offline-pc-deployment.md`) 의 §3.2 에 따라, 향후 발송 결과물을
Drive 가 아닌 다음 옵션으로 공유하는 것이 우선 검토 대상입니다.

1. 로컬 디스크 + 사내 GitLab/GitHub
2. 사내 SMB 파일 서버 (네트워크 드라이브 매핑)
3. OneDrive / SharePoint (사내 M365)

Drive 재도입은 보안팀 승인이 어렵다는 전제로 후순위입니다.
