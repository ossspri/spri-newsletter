# SPRi Newsletter — 동료 PC 30분 셋업 가이드 (Windows)

> 대상 독자: 동료 1인 운영자 (Windows 10/11, Google Drive 차단된 사내망)
> 추정 소요 시간: 30분
> 산출 결과: `http://127.0.0.1:5000` 웹 UI 가 열리고, Focus 탭에서 Gmail 발송 가능

---

---

## 1. Python 설치 (자동)

> `setup_local.bat`가 Python을 자동 감지하여, 미설치 시 자동으로 다운로드+설치합니다.
> **수동 설치가 필요 없습니다.** 아래는 자동 설치가 실패할 경우의 수동 절차입니다.

### 자동 설치가 실패한 경우 (사내망 다운로드 차단 등)

1. https://www.python.org/downloads/ 에 접속
2. **Download Python 3.11.x** 클릭하여 설치 파일 다운로드
3. 설치 시 **"Add python.exe to PATH" 반드시 체크**
4. **Install Now** 클릭
5. 설치 확인: `Win+R` → `cmd` → `python --version`

> **사내 프록시 환경**: 다운로드나 pip install 시 오류가 나면 `docs\TROUBLESHOOTING.md` 참고.

---

## 2. 압축 해제

1. zip 을 **한글이 없는 경로**에 해제합니다.
   - 권장: `C:\spri-newsletter\` 또는 `D:\work\spri-newsletter\`
   - 비권장: `C:\사용자\이름\바탕화면\` (한글 인코딩 이슈 가능)

---

## 3. 시크릿 배치

### 3-1. `.env` 파일 덮어쓰기

메일로 받은 `.env` 파일을 **설치 폴더 최상위**에 덮어쓰기합니다.
```
<설치폴더>\.env    ← 여기에 덮어쓰기
```

> zip에 기본 `.env`가 포함되어 있지만 키 값이 비어 있습니다.
> 메일로 받은 파일로 교체하면 API 키가 자동 설정됩니다.

### 3-2. OAuth client JSON

> zip에 이미 `credentials/google_credentials.json`이 포함되어 있다면 이 단계는 건너뛰세요.

zip에 포함되어 있지 않은 경우, 메일로 받은 `google_credentials.json` 을 다음 위치에 배치합니다.
```
<설치폴더>\credentials\google_credentials.json
```

---

## 4. 셋업 스크립트 실행

설치 폴더에서 다음 파일을 더블클릭합니다.
```
scripts\win\setup_local.bat
```

화면 안내에 따라 순서대로 진행합니다.
1. `.env` 가 없으면 메모장이 열립니다 → API 키 입력 후 저장
2. `credentials\google_credentials.json` 존재 확인
3. Python 미설치 시 자동 다운로드 + 설치 (1-2분 소요)
4. `.venv` 가상환경 생성 + 의존성 설치
5. 첫 OAuth 트리거 — 브라우저가 자동으로 열립니다.
   - **반드시 팀 공용 Gmail 계정으로 로그인** → "Gmail 보내기", "Gmail 읽기" 권한 동의
   - 개인 Gmail이 Chrome에 로그인되어 있으면 "다른 계정 사용"을 클릭하세요
   - 동의 후 브라우저 창은 그대로 두세요 (스크립트가 30초 후 자동 종료)

> **주의**: 개인 Gmail로 로그인하면 개인 계정에서 뉴스레터가 발송됩니다.
> 팀 계정 정보는 메인PC에서 확인하세요.

성공 시 `credentials\google_token.json` 이 생성됩니다. 이 파일은 **이 PC 전용**입니다.
다른 PC 의 token 파일을 복사해 쓰지 마세요 (refresh 충돌 위험).

---

## 5. 서버 시작

```
scripts\win\start_server.bat
```

콘솔 창이 열리면 약 10초 후 다음 주소에 접속합니다.
```
http://127.0.0.1:5000
```

---

## 6. 첫 Focus 뉴스레터 발송

1. 상단 **Focus** 탭 클릭
2. 좌측 큐레이션 영역에서:
   - "URL 기사 추가" → 발송하고 싶은 기사 URL 입력
   - "PDF 보고서 업로드" → 첨부할 PDF 선택
3. 우측 "수신자" 영역에 **자기 이메일 주소를 먼저 1개 추가** 하여 테스트
4. "생성" 클릭 → Claude 가 본문 초안 작성 (수십 초 소요)
5. "미리보기" 로 본문 검토
6. "발간" 클릭 → 5분 이내 Gmail Sent 폴더에 메일이 도착하면 성공
7. 수신된 메일의 **발신자가 팀 공용 Gmail 주소**인지 확인

> 처음 발송 시 수신자 리스트가 비어 있어 오류가 나면, `config.windows-portable.yaml`
> 의 `recipients.focus` 에 이메일을 추가하거나 UI 에서 직접 추가하세요.
>
> 발신자가 개인 Gmail로 표시되면 토큰을 재발급해야 합니다:
> `credentials\google_token.json` 삭제 후 `setup_local.bat` 재실행.

---

## 7. 일상 운영

| 상황 | 명령 |
|---|---|
| 서버 시작 | `scripts\win\start_server.bat` 더블클릭 |
| 서버 종료 | 콘솔 창 닫기 또는 `scripts\win\stop_server.bat` |
| 의존성 업데이트 | 메인PC에서 새 zip 배포 → 압축 해제 후 `setup_local.bat` 재실행 |
| 보낸 메일 이력 확인 | `data\db\newsletter_log.csv`, Gmail Sent 폴더 |

---

## 문제 해결

`docs\TROUBLESHOOTING.md` 와 `docs\FAQ_DRIVE_BLOCKED.md` 를 참고하세요.
