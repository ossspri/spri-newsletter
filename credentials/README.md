# credentials/ 폴더

이 폴더는 Google OAuth 인증 파일을 보관하는 위치입니다.
실제 시크릿 파일은 git에 커밋되지 않습니다 (`.gitignore`로 보호).

## 배치해야 하는 파일

### `google_credentials.json` (필수)
메인 PC 관리자가 메일로 전달한 OAuth Desktop client JSON을 **이 폴더에 그대로** 배치하세요.
파일명은 반드시 `google_credentials.json` 이어야 합니다.

```
credentials\google_credentials.json
```

## 자동 생성되는 파일

### `google_token.json`
`scripts\win\setup_local.bat` 첫 실행 시 OAuth 브라우저 동의를 마치면 자동 생성됩니다.
- **이 파일은 PC별 고유 파일**입니다. 다른 PC의 token을 복사해서 쓰지 마세요 (refresh 충돌 위험).
- 분실 시 `google_token.json` 만 삭제 후 setup_local.bat 또는 서버 첫 기동에서 재인증하면 됩니다.

## 참고 파일

### `google_credentials.sample.json`
형식 참고용 placeholder입니다. 실제 인증에는 사용되지 않으며, `<REPLACE_WITH_REAL_VALUE>` 가 들어 있습니다.
**삭제하지 마세요.** 신규 PC 셋업 시 형식을 확인하는 용도입니다.

## 주의

- 이 폴더의 실제 시크릿 파일들 (`google_credentials.json`, `google_token.json`) 은 절대 git에 커밋되지 않습니다.
- 메일·메신저로 시크릿을 공유할 때는 사내 보안 정책을 준수하세요.
