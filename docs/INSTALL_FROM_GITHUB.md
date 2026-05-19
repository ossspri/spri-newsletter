# SPRi Newsletter — GitHub 저장소로부터 셋업 (Windows)

> 대상 독자: 동료 1인 운영자 (Windows 10/11)
> 추정 소요 시간: 30분
> 산출 결과: `http://127.0.0.1:5000` 웹 UI 가 열리고, **Focus 탭**에서 Gmail 발송 가능

이 문서는 신규 공개 저장소 `https://github.com/ossspri/spri-newsletter` 를 `git clone` 으로 받아 셋업하는 절차입니다.
기존 zip 배포 방식 가이드는 `docs\DEPLOY_WINDOWS.md` 에 보존되어 있으니 백업으로 참고하세요.

---

## 1. 사전 요구사항

- Windows 10 또는 11
- 설치 경로에 **한글이 포함되지 않아야** 합니다
  - 권장: `C:\spri-newsletter\`
  - 비권장: `C:\사용자\이름\바탕화면\...`
- 인터넷 접속 (사내 프록시 사용 시 `docs\TROUBLESHOOTING.md` 참고)

---

## 2. Git for Windows 설치

1. https://git-scm.com/download/win 접속
2. 64-bit 설치 파일 다운로드 후 실행
3. **모든 옵션은 기본값**으로 두고 Next 클릭 (특히 PATH 옵션은 기본인 "Git from the command line..." 유지)
4. 설치 완료 후 새 cmd 창에서 확인:
   ```
   git --version
   ```
   `git version 2.x.x ...` 가 출력되면 OK

> 자동 설치 스크립트(`scripts\win\install_git.bat`)도 포함되어 있지만, **clone 전에는 Git이 먼저 있어야 하므로** 수동 설치를 권장합니다.

---

## 3. 저장소 clone

cmd 창을 열고 다음을 순서대로 실행:

```
cd C:\
git clone https://github.com/ossspri/spri-newsletter.git spri-newsletter
cd spri-newsletter
```

이후 모든 작업은 `C:\spri-newsletter\` 폴더 기준입니다.

---

## 4. 시크릿 배치 (메일 첨부 파일 2개)

메인 PC 관리자가 메일로 전달한 2개 파일을 다음 위치에 배치합니다.

### 4-1. `.env`

메일로 받은 `.env` 파일을 저장소 최상위에 배치(덮어쓰기)합니다.
```
C:\spri-newsletter\.env
```

> 저장소에는 `.env.example` (빈 템플릿) 만 있고, `.env` 자체는 git에서 제외되어 있습니다.

### 4-2. `google_credentials.json`

메일로 받은 OAuth Desktop client JSON 파일을 `credentials\` 폴더에 배치합니다.
```
C:\spri-newsletter\credentials\google_credentials.json
```

> `credentials\google_credentials.sample.json` 은 형식 참고용 placeholder입니다 (인증에 사용되지 않음). 실제 인증은 `google_credentials.json` 으로 이루어집니다.

---

## 5. 초기 셋업 실행

탐색기에서 다음 파일을 **더블클릭**합니다.
```
scripts\win\setup_local.bat
```

화면 안내(6단계) 그대로 진행하면 됩니다.

1. **Git 설치 확인** — 이미 설치되어 있으면 즉시 통과
2. **.env 확인** — 없으면 메모장이 열림 (이미 배치했으면 통과)
3. **credentials 확인** — `google_credentials.json` 존재 확인
4. **Python 확인** — 미설치 시 자동 다운로드+설치 (1-2분)
5. **.venv 생성 + 의존성 설치**
6. **OAuth 첫 동의** — 브라우저가 자동으로 열립니다
   - **반드시 팀 공용 Gmail 계정으로 로그인** 하세요
   - 개인 Gmail이 Chrome에 로그인되어 있으면 **"다른 계정 사용"** 을 클릭
   - 동의 후 브라우저 창은 그대로 두세요 (스크립트가 30초 후 자동 종료)

성공 시 `credentials\google_token.json` 이 생성됩니다. **이 파일은 이 PC 전용**이며, 다른 PC의 token을 복사해 쓰지 마세요.

---

## 6. 서버 시작 & Focus 탭 확인

탐색기에서 다음 파일을 더블클릭:
```
scripts\win\start_server.bat
```

브라우저에서 접속:
```
http://127.0.0.1:5000
```

상단 메뉴에 **Focus 탭만 보이는 것이 정상**입니다 (Daily / Weekly 탭은 숨김 처리됨).
이는 `config.windows-portable.yaml` 의 `focus_menu_only: true` 설정에 의한 동작입니다.

---

## 7. 업데이트 받기

메인 PC 관리자가 새 버전 알림을 보내면, 탐색기에서 다음 파일을 더블클릭:
```
scripts\win\update.bat
```

내부적으로 다음을 수행합니다:
1. Git 설치 확인
2. `git pull --ff-only` — 최신 코드 받기
3. `pip install -r requirements.txt` — 의존성 동기화
4. 최근 5개 commit 표시

> `git pull` 실패 시 (로컬 변경사항 충돌 등) 메시지가 표시됩니다. 직접 수정한 파일이 없다면 메인 PC 관리자에게 문의하세요.

---

## 8. 일상 운영

| 동작 | 실행 파일 |
| --- | --- |
| 서버 시작 | `scripts\win\start_server.bat` |
| 서버 중지 | `scripts\win\stop_server.bat` |
| 업데이트 받기 | `scripts\win\update.bat` |

서버 시작 후 브라우저에서 `http://127.0.0.1:5000` 접속 → Focus 탭에서 작업.

---

## 9. 문제 해결

- 일반 트러블슈팅: `docs\TROUBLESHOOTING.md`
- Google Drive 사내망 차단 관련: `docs\FAQ_DRIVE_BLOCKED.md`
- 셋업 실패: setup_local.bat 마지막에 표시된 에러 메시지를 캡처하여 메인 PC 관리자에게 전달
