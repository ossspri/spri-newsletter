# 트러블슈팅 — SPRi Newsletter on Windows

> Quick index
> - [한글이 깨져 보입니다](#1-한글이-깨져-보입니다)
> - [pip install 이 SSL/프록시 에러로 실패합니다](#2-pip-install-이-ssl--프록시-에러로-실패합니다)
> - [OAuth 동의 후 브라우저가 무한 로딩됩니다](#3-oauth-동의-후-브라우저가-무한-로딩됩니다)
> - [`recipients.focus` 가 없다는 오류](#4-recipientsfocus-가-없다는-오류)
> - [`port 5000 already in use`](#5-port-5000-already-in-use)
> - [`msvcrt` 락 경합 / 파일이 사용 중](#6-msvcrt-락-경합--파일이-사용-중)
> - [`pdfplumber` 가 PDF 를 못 읽습니다](#7-pdfplumber-가-pdf-를-못-읽습니다)
> - [Anthropic API 호출이 SSL 인증서 에러](#8-anthropic-api-호출이-ssl-인증서-에러)

---

## 1. 한글이 깨져 보입니다

증상: 콘솔에서 한글이 `?` 또는 깨진 문자로 출력됩니다.

원인: Windows 콘솔의 기본 코드페이지(CP949)와 Python UTF-8 출력 충돌.

해결:
- 본 zip 의 모든 `.bat` 는 `chcp 65001` 을 자동 수행합니다.
- 직접 명령 프롬프트에서 실행할 때는 다음을 먼저 입력하세요.
  ```
  chcp 65001
  set PYTHONIOENCODING=utf-8
  ```
- 영구 설정: 시스템 환경변수에 `PYTHONUTF8=1` 추가.

---

## 2. pip install 이 SSL / 프록시 에러로 실패합니다

증상: `setup_local.bat` 의 pip 단계에서 `SSLCertVerificationError` 또는 `ProxyError`.

해결:
1. 사내 프록시가 설정되어 있다면 환경변수에 다음을 추가.
   ```
   set HTTP_PROXY=http://proxy.your-company:8080
   set HTTPS_PROXY=http://proxy.your-company:8080
   ```
2. 사내 CA 인증서 사용 시:
   ```
   set PIP_CERT=C:\path\to\corporate-ca-bundle.pem
   ```
3. 위 두 변수를 설정한 후 `setup_local.bat` 를 다시 실행.
4. 그래도 안 되면 wheel 동봉 zip 을 메인 운영자에게 요청 (오프라인 설치).

---

## 3. OAuth 동의 후 브라우저가 무한 로딩됩니다

증상: Google 동의 후 `http://localhost:NNNNN/?code=...` 로 리다이렉트되었으나 페이지가 영원히 로딩.

원인: 사내 방화벽 / EDR 이 localhost loopback 콜백을 차단.

해결:
1. Windows 보안 → 방화벽 → 인바운드 규칙에서 `python.exe` 의 localhost 통신 허용.
2. 그래도 안 되면 `google_auth.py` 의 `run_local_server(port=0)` 을 고정 포트로 (예: 8765)
   변경 후 해당 포트만 방화벽 허용 — 메인 운영자에게 패치 요청.
3. EDR (사내 보안 솔루션) 이 차단하는 경우 보안팀에 예외 요청.

---

## 4. `recipients.focus` 가 없다는 오류

증상: Focus 탭에서 "발간" 클릭 시 `ValueError: recipients가 비어 있습니다` 또는 KeyError.

해결:
- `config.windows-portable.yaml` 의 `recipients.focus` 가 빈 리스트로 정의되어 있는지 확인.
- UI 상단의 수신자 입력란에 본인 이메일을 추가 후 다시 시도.
- 영구 등록: `config.windows-portable.yaml` 의 `recipients.focus:` 아래에 이메일을 줄단위로 추가.

```yaml
recipients:
  focus:
    - "you@spri.kr"
```

---

## 5. `port 5000 already in use`

증상: `start_server.bat` 실행 시 포트 충돌.

해결:
```
scripts\win\stop_server.bat
```
또는 수동 종료:
```
netstat -ano | findstr :5000
taskkill /F /PID <위에서 본 PID>
```

---

## 6. `msvcrt` 락 경합 / 파일이 사용 중

증상: `data\db\*.csv` 쓰기가 일시적으로 막힙니다. 로그: `msvcrt.locking ... Permission denied`.

원인: 같은 CSV 에 두 프로세스가 동시에 쓰려는 경합 (예: 두 번째 `start_server.bat` 가 중복 실행).

해결:
- 본 시스템은 advisory lock 으로 재시도하므로 대부분 자동 회복합니다.
- 지속될 경우 중복 실행된 콘솔을 종료한 뒤 다시 시작하세요.
- Excel 로 CSV 를 열어 둔 상태라면 닫아주세요 (Excel 이 파일 공유 잠금을 잡습니다).

---

## 7. `pdfplumber` 가 PDF 를 못 읽습니다

증상: Focus 탭에서 PDF 업로드 후 추출이 실패.

원인 후보:
- 이미지 기반 스캔 PDF (텍스트 레이어 없음) — pdfplumber 로 처리 불가.
- 파일 손상 또는 암호화 PDF.

해결:
- 텍스트 레이어가 있는 PDF 로 교체.
- 스캔 PDF 라면 OCR 도구로 텍스트 레이어를 추가한 후 다시 업로드.

---

## 8. Anthropic API 호출이 SSL 인증서 에러

증상: Claude 본문 생성 시 `SSLCertVerificationError` 또는 `unable to get local issuer certificate`.

원인: 사내 SSL inspection 프록시 (Zscaler, Bluecoat 등) 가 인증서를 재서명.

해결:
1. 환경변수로 사내 CA bundle 지정:
   ```
   set REQUESTS_CA_BUNDLE=C:\path\to\corporate-ca-bundle.pem
   set SSL_CERT_FILE=C:\path\to\corporate-ca-bundle.pem
   ```
2. `.env` 에 위 두 줄을 추가하면 자동 로드됩니다.
3. 그래도 안 되면 사내 보안팀에 `api.anthropic.com` 우회(allowlist) 요청.

---

## 그 외

해결되지 않는 문제는 다음 정보를 메인 운영자에게 전달하세요.
1. `logs\spri.log` 마지막 100줄
2. 실행한 `.bat` 이름과 입력한 동작
3. 콘솔 창의 에러 메시지 스크린샷
