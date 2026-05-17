# SPRi Newsletter — 동료 PC 30분 셋업 가이드 (Windows)

> 대상 독자: 동료 1인 운영자 (Windows 10/11, Google Drive 차단된 사내망)
> 추정 소요 시간: 30분
> 산출 결과: `http://127.0.0.1:5000` 웹 UI 가 열리고, Focus 탭에서 Gmail 발송 가능

---

## 0. 사전 준비물

| 항목 | 비고 |
|---|---|
| Windows 10 22H2 또는 Windows 11 | UTF-8 코드페이지 활성 권장 |
| 빈 디스크 2GB+ | zip 추출 후 약 300MB |
| 인터넷 | Anthropic API + Gmail HTTPS 통과 필수 (Drive 차단은 무관) |
| Chrome 또는 Edge 최신 | OAuth 동의용 |
| `spri-newsletter-v<날짜>.zip` | 메인 운영자가 전달 |
| OAuth client JSON | zip에 이미 포함됨 (없으면 메인 운영자에게 요청) |
| 팀 공용 Gmail 계정 정보 | 메인 운영자에게 확인 (OAuth 인증 시 이 계정으로 로그인) |
| Anthropic API key | 동료가 자기 키 발급 권장 |

---

## 1. Python 설치

> 이미 Python 3.11 이상이 설치되어 있다면 이 단계를 건너뛰세요.
> 확인 방법: `Win+R` → `cmd` → `python --version` 입력 → `Python 3.11.x` 이상이면 OK.

1. https://www.python.org/downloads/ 에 접속
2. **Download Python 3.11.x** (또는 3.12.x) 클릭하여 설치 파일 다운로드
3. 설치 파일 실행 시 **첫 화면에서 반드시 아래 두 항목 체크**:
   - ☑ **Add python.exe to PATH** ← 체크 안 하면 이후 모든 단계가 실패합니다
   - ☑ Use admin privileges when installing py.exe
4. **Install Now** 클릭 (기본 설정 그대로 설치)
5. 설치 완료 후 **"Disable path length limit"** 버튼이 보이면 클릭 (긴 경로 지원)
6. 설치 확인:
   ```
   Win+R → cmd 실행 후:
   python --version
   pip --version
   ```
   둘 다 버전이 출력되면 성공.

> **사내 프록시 환경**: pip install 시 SSL 오류가 나면 `docs\TROUBLESHOOTING.md`의
> "pip SSL/사내 프록시" 절을 참고하세요.

---

## 2. 압축 해제

1. zip 을 **한글이 없는 경로**에 해제합니다.
   - 권장: `C:\spri-newsletter\` 또는 `D:\work\spri-newsletter\`
   - 비권장: `C:\사용자\이름\바탕화면\` (한글 인코딩 이슈 가능)
2. zip 의 SHA-256 을 메인 운영자가 전달한 값과 비교해 무결성 확인.
   ```
   certutil -hashfile spri-newsletter-v<날짜>.zip SHA256
   ```

> [SCREENSHOT placeholder] 압축 해제 후 디렉토리 구조 (`scripts/`, `data/`, `docs/`, `setup_local.bat` 등 확인)

---

## 3. 시크릿 배치

### 3-1. OAuth client JSON

> zip에 이미 `credentials/google_credentials.json`이 포함되어 있다면 이 단계는 건너뛰세요.

zip에 포함되어 있지 않은 경우, 메인 운영자에게 받은 `google_credentials.json` 을 다음 위치에 배치합니다.
```
<설치폴더>\credentials\google_credentials.json
```

> [SCREENSHOT placeholder] credentials 폴더에 JSON 파일이 놓인 모습

### 3-2. `.env` (자동 안내)

다음 단계의 `setup_local.bat` 가 `.env` 가 없을 때 자동으로 `.env.example` 을 복사하고
메모장을 열어 줍니다. 메모장에서 최소 다음 키를 입력 후 저장하세요.
```
CLAUDE_API_KEY=sk-ant-...   # 동료 본인의 키
GNEWS_API_KEY=               # Focus 만 쓰면 빈 값 OK
```

---

## 4. 셋업 스크립트 실행

설치 폴더에서 다음 파일을 더블클릭합니다.
```
scripts\win\setup_local.bat
```

스크립트가 다음을 자동 수행합니다.
1. `.env` 가 없으면 메모장 자동 오픈 → 키 입력 후 저장
2. `credentials\google_credentials.json` 존재 확인
3. `.venv` 가상환경 생성 + `pip install -r requirements.txt`
4. 첫 OAuth 트리거 — 브라우저가 자동으로 열립니다.
   - **반드시 팀 공용 Gmail 계정으로 로그인** → "Gmail 보내기", "Gmail 읽기" 권한 동의
   - 개인 Gmail이 Chrome에 로그인되어 있으면 "다른 계정 사용"을 클릭하세요
   - 동의 후 브라우저 창은 그대로 두세요 (스크립트가 30초 후 자동 종료)

> **주의**: 개인 Gmail로 로그인하면 개인 계정에서 뉴스레터가 발송됩니다.
> 팀 계정 정보는 메인 운영자에게 문의하세요.

> [SCREENSHOT placeholder] OAuth 동의 화면 (Gmail 권한 2개만 노출됨, Drive 권한 없음)

성공 시 `credentials\google_token.json` 이 생성됩니다. 이 파일은 **이 PC 전용**입니다.
메인 운영자나 다른 PC 의 token 파일을 복사해 쓰지 마세요 (refresh 충돌 위험).

---

## 5. 서버 시작

```
scripts\win\start_server.bat
```

콘솔 창이 열리면 약 10초 후 다음 주소에 접속합니다.
```
http://127.0.0.1:5000
```

> [SCREENSHOT placeholder] Web UI 메인 화면 (Daily / Weekly / Focus 탭)

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
| 의존성 업데이트 | 메인 운영자가 새 zip 배포 → 압축 해제 후 `setup_local.bat` 재실행 |
| 보낸 메일 이력 확인 | `data\db\newsletter_log.csv`, Gmail Sent 폴더 |

---

## 문제 해결

`docs\TROUBLESHOOTING.md` 와 `docs\FAQ_DRIVE_BLOCKED.md` 를 참고하세요.

비상 연락처: (메인 운영자 정보)
