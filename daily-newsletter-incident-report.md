# Daily Newsletter 워크플로우 장애 분석 보고서

**날짜**: 2026-05-30  
**워크플로우**: Daily Newsletter (KST 07:30) — `daily-newsletter.yml`  
**저장소**: martinyoo/newsletter-system

---

## 1. 증상 요약

- 2026-05-21(Run #6) ~ 2026-05-24(Run #9): 스케줄 실행 4회 연속 실패
- 2026-05-25 ~ 2026-05-29: 스케줄 자동 실행 없음 (GitHub 스케줄러 중단)
- 2026-05-29(Run #10): 수동 실행 → 실패
- 2026-05-30(Run #11): 수동 실행 → **성공** ✅

| Run | 날짜 (KST) | 트리거 | 결과 | 소요 |
|-----|-----------|--------|------|------|
| #6  | May 21 08:49 | Scheduled | ❌ 실패 | 1m 23s |
| #7  | May 22 08:35 | Scheduled | ❌ 실패 | 2m 34s |
| #8  | May 23 08:40 | Scheduled | ❌ 실패 | 1m 37s |
| #9  | May 24 08:31 | Scheduled | ❌ 실패 | 1m 49s |
| #10 | May 29 15:32 | 수동 | ❌ 실패 | 1m 44s |
| #11 | May 30 (수동) | 수동 | ✅ 성공 | 2m 28s |

---

## 2. 근본 원인

### 2-1. Google OAuth 토큰 만료 (`invalid_grant`)

`GOOGLE_TOKEN_B64` 시크릿에 저장된 OAuth 토큰이 만료되어 갱신 실패.

```
WARNING: 토큰 갱신 실패, 재인증 진행:
('invalid_grant: Bad Request', {'error': 'invalid_grant', 'error_description': 'Bad Request'})
```

### 2-2. Headless 환경에서 브라우저 인증 시도

토큰 갱신 실패 후 코드가 `flow.run_local_server()`를 호출하여 브라우저 실행 시도.
GitHub Actions는 headless 환경이므로 브라우저가 없어 최종 오류 발생.

```
File "google_auth.py", line 87, in get_google_credentials
    creds = flow.run_local_server(port=0)
webbrowser.Error: could not locate runnable browser
Error: Process completed with exit code 1.
```

---

## 3. 수행한 조치 (2026-05-29)

| 시각 (KST) | 조치 | 커밋/작업 |
|-----------|------|----------|
| 15:32 | Run #10 수동 실행 → 실패 확인 | — |
| 17:03 | `fix(google_auth)`: CI 환경 감지 → fail-fast 패치 | `c85201f` |
| 당일 | Google OAuth 재인증 후 `GOOGLE_TOKEN_B64` 시크릿 갱신 | GitHub Secrets |
| 당일 | 발신자 변경: 기존 → `ossspri@gmail.com` | — |

**fix 내용**: `CI=true` 환경 감지 시 `flow.run_local_server()` 대신 명확한 에러 메시지로 즉시 종료.

---

## 4. 오늘(May 30) 07:30 KST 자동 실행이 안된 이유

스케줄 실행(#6~#9)이 4회 연속 실패하자 **GitHub Actions 스케줄러가 자동으로 중단**됨.

- GitHub은 scheduled 워크플로우가 반복 실패하면 스케줄러를 드롭하는 동작을 함
- May 24(#9) 이후 May 30까지 약 6일간 자동 실행 없음
- 수동 실행(#11) 성공 이후 내일부터 스케줄 재개 예상

> **참고**: GitHub Actions cron은 `30 22 * * *` (UTC) = KST 07:30.  
> 위치: `.github/workflows/daily-newsletter.yml` 6번 줄

---

## 5. 현재 상태 및 후속 확인 사항

- ✅ Run #11 수동 실행 성공 (2026-05-30, 2m 28s, 발신자 ossspri@gmail.com)
- ⏳ **2026-05-31 07:30 KST**: 스케줄 자동 실행 재개 여부 확인 필요
- 이후 연속 성공 시 정상 운영으로 복귀 판단
