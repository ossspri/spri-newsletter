# SPRi Newsletter — GitHub 저장소로부터 셋업 (Windows)

> 대상 독자: 동료 1인 운영자 (Windows 10/11)
> 추정 소요 시간: 30분
> 산출 결과: `http://127.0.0.1:5000` 웹 UI 가 열리고, **Focus 탭**에서 Gmail 발송 가능

이 문서는 신규 공개 저장소 `https://github.com/ossspri/spri-newsletter` 를 `git clone` 으로 받아 셋업하는 절차입니다.

---

## 1. 사전 요구사항
- Windows 10 또는 11
- 설치 경로에 **한글이 포함되지 않아야** 합니다
  - 권장 (자동 설치 위치): `C:\spri-newsletter\`
- 인터넷 접속 (사내 프록시 사용 시 `docs\TROUBLESHOOTING.md` 참고)
- 메인PC로부터 메일 전달된 첨부파일 2개: `.env`, `google_credentials.json`
- 메일발송용 부서공용 gmail 접속 (개인 gmail 로 발송불가)

---

## 2. 부트스트랩 (`setup_local.bat` 한 파일 다운로드 → 더블클릭)

`setup_local.bat` 한 파일이 다음을 **모두 자동** 처리합니다:

1. Git for Windows 설치 (미설치 시)
2. `https://github.com/ossspri/spri-newsletter` → `C:\spri-newsletter\` 로 `git clone`
3. 시크릿 파일 배치 대기 ([3장](#3-시크릿-배치-메일-첨부-파일-2개))
4. Python·`.venv`·의존성 자동 설치 + OAuth 첫 동의 ([4장](#4-본-셋업-자동-진행-내용))

### 2-1. setup_local.bat 다운로드

- **방법 A**: 브라우저로 아래 URL 우클릭 → **다른 이름으로 링크 저장** → 파일명 `setup_local.bat` 로 바탕화면에 저장
  ```
  https://raw.githubusercontent.com/ossspri/spri-newsletter/main/scripts/win/setup_local.bat
  ```
- **방법 B**: cmd 한 줄
  ```
  curl -L -o "%USERPROFILE%\Desktop\setup_local.bat" https://raw.githubusercontent.com/ossspri/spri-newsletter/main/scripts/win/setup_local.bat
  ```

### 2-2. 더블클릭하여 실행

저장한 `setup_local.bat` 을 더블클릭하면 콘솔 창에서 부트스트랩이 시작됩니다.

- **Bootstrap 1/3**: Git 자동 설치 (Git for Windows 2.45.2 silent install). 이미 있으면 즉시 통과.
- **Bootstrap 2/3**: `C:\spri-newsletter\` 에 저장소 clone
- **Bootstrap 3/3**: 시크릿 파일 배치 대기 → 다음 장 진행 후 아무 키나 눌러 계속

> 바탕화면의 `setup_local.bat` 사본은 부트스트랩 1회용입니다. 저장소 내부에도 동일 파일이 있으니 완료 후 삭제해도 됩니다.
>
> **자동 Git 설치 실패 시**: 사내 프록시·다운로드 차단 등으로 자동 설치가 막히면 https://git-scm.com/download/win 에서 64-bit 인스톨러를 직접 받아 기본 옵션으로 설치 후 부트스트랩을 재실행하세요.

---

## 3. 시크릿 배치 (메일 첨부 파일 2개)

**Bootstrap 3/3** 단계에서 콘솔이 입력을 기다리는 동안, 메일로 받은 두 파일을 다음 위치에 복사합니다.

| 파일 | 배치 위치 |
| --- | --- |
| `.env` | `C:\spri-newsletter\.env` |
| `google_credentials.json` | `C:\spri-newsletter\credentials\google_credentials.json` |

두 파일이 모두 배치되면 콘솔 창에서 **아무 키나 누르면** 자동으로 다음(4장) 본 셋업으로 진행됩니다. 파일이 누락된 경우 경고가 표시되고 다시 대기 상태로 돌아갑니다.

> 저장소에는 `.env.example` (빈 템플릿) 과 `credentials\google_credentials.sample.json` (형식 참고용 placeholder) 만 포함되어 있고, 실제 시크릿은 git에서 제외되어 있습니다.

---

## 4. 본 셋업 (자동 진행 내용)

3장에서 키를 누르면 cloned 된 `C:\spri-newsletter\scripts\win\setup_local.bat` 이 자동으로 이어 실행되며 6단계를 진행합니다. **수동 작업은 STEP 6의 OAuth 동의 클릭뿐**입니다.

| STEP | 동작 | 수동 작업 |
| --- | --- | --- |
| 1/6 | Git 설치 재확인 | — |
| 2/6 | `.env` 확인 (없으면 메모장 열림) | — (3장에서 배치 완료) |
| 3/6 | `credentials\google_credentials.json` 확인 | — |
| 4/6 | Python 3.11 설치 확인 — 미설치 시 자동 다운로드+설치 (1-2분) | — |
| 5/6 | `.venv` 생성 + `pip install -r requirements.txt` | — |
| 6/6 | OAuth 첫 동의 — 브라우저 자동 오픈 | **팀 공용 Gmail로 로그인 후 동의 클릭** |

### STEP 6 주의사항

- **반드시 팀 공용 Gmail 계정으로 로그인** 하세요
- 개인 Gmail이 Chrome에 로그인되어 있으면 **"다른 계정 사용"** 을 클릭
- 동의 후 브라우저 창은 그대로 두세요 (스크립트가 30초 후 자동 종료)

성공 시 `credentials\google_token.json` 이 생성됩니다. **이 파일은 이 PC 전용**이며, 다른 PC의 token을 복사해 쓰지 마세요.

---

## 5. 서버 시작 & Focus 탭 확인

탐색기에서 다음 파일을 더블클릭:
```
C:\spri-newsletter\scripts\win\start_server.bat
```

브라우저에서 접속:
```
http://127.0.0.1:5000
```

상단 메뉴에 **Focus 탭만 보이는 것이 정상**입니다 (Daily / Weekly 탭은 숨김 처리됨).
이는 `config.windows-portable.yaml` 의 `focus_menu_only: true` 설정에 의한 동작입니다.

---

## 6. 업데이트 받기

메인 PC 관리자가 새 버전 알림을 보내면, 탐색기에서 다음 파일을 더블클릭:
```
C:\spri-newsletter\scripts\win\update.bat
```

내부적으로 다음을 수행합니다:
1. Git 설치 확인
2. `git pull --ff-only` — 최신 코드 받기
3. `pip install -r requirements.txt` — 의존성 동기화
4. 최근 5개 commit 표시

> `git pull` 실패 시 (로컬 변경사항 충돌 등) 메시지가 표시됩니다. 직접 수정한 파일이 없다면 메인 PC 관리자에게 문의하세요.

---

## 7. 일상 운영

| 동작 | 실행 파일 |
| --- | --- |
| 서버 시작 | `scripts\win\start_server.bat` |
| 서버 중지 | `scripts\win\stop_server.bat` |
| 업데이트 받기 | `scripts\win\update.bat` |

서버 시작 후 브라우저에서 `http://127.0.0.1:5000` 접속 → Focus 탭에서 작업.

---

## 8. 문제 해결

- 일반 트러블슈팅: `docs\TROUBLESHOOTING.md`
- Google Drive 사내망 차단 관련: `docs\FAQ_DRIVE_BLOCKED.md`
- 셋업 실패: setup_local.bat 마지막에 표시된 에러 메시지를 캡처하여 메인 PC 관리자에게 전달
