"""src/git_sync.py — 발행 결과물(.md, .csv) git 자동 동기화.

P0(2026-05-13): 동료들이 ``git pull``로 최신 뉴스레터 원고와 발송 이력 CSV를
받을 수 있도록, publish 전후로 git pull/commit/push를 자동 수행한다.

흐름:
  - publish 직전: ``pull_or_fail()`` → ``git pull --rebase``. 충돌 시 발송 차단.
  - publish 직후: ``commit_and_push(type, date)`` → ``data/newsletters/``,
    ``data/db/`` 변경분을 add + commit + push.

Config:
  features.git_autosync (bool, default False): 전체 토글
  features.git_autosync_dry_run (bool, default False): 실제 git 명령 없이 로그만
"""
import logging
import subprocess
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

DEFAULT_SYNC_PATHS = ("data/newsletters", "data/db")


class GitSyncError(Exception):
    """git 동기화 단계에서 발송을 차단해야 하는 실패 (pull rebase 충돌 등)."""


class GitSync:
    def __init__(
        self,
        repo_dir: Path | str,
        config: Optional[dict] = None,
        paths: Optional[Iterable[str]] = None,
    ):
        self.repo_dir = Path(repo_dir)
        features = (config or {}).get("features", {}) if config else {}
        self.enabled = bool(features.get("git_autosync", False))
        self.dry_run = bool(features.get("git_autosync_dry_run", False))
        self.paths = tuple(paths) if paths else DEFAULT_SYNC_PATHS

    def _run(
        self, args: list[str], check: bool = True
    ) -> subprocess.CompletedProcess:
        cmd = ["git", "-C", str(self.repo_dir), *args]
        logger.debug("git_sync: %s", " ".join(cmd))
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=check,
        )

    def _has_remote(self) -> bool:
        try:
            self._run(["remote", "get-url", "origin"])
            return True
        except subprocess.CalledProcessError:
            return False

    def pull_or_fail(self) -> dict:
        """publish 직전 호출: ``git pull --rebase origin``.

        충돌 시 ``GitSyncError`` raise → 발송 차단.
        flag off / remote 없음 / dry-run인 경우 no-op.

        반환: {"action": "pulled"|"skipped", "reason": str|None}
        """
        if not self.enabled:
            return {"action": "skipped", "reason": "disabled"}
        if not self._has_remote():
            logger.info("git_sync.pull: origin remote 없음 — skip")
            return {"action": "skipped", "reason": "no-remote"}
        if self.dry_run:
            logger.info("[dry-run] git pull --rebase origin")
            return {"action": "skipped", "reason": "dry-run"}

        try:
            result = self._run(["pull", "--rebase", "origin"])
            logger.info("git_sync.pull: %s", result.stdout.strip() or "OK")
            return {"action": "pulled", "reason": None}
        except subprocess.CalledProcessError as e:
            self._run(["rebase", "--abort"], check=False)
            stderr = (e.stderr or "").strip()
            raise GitSyncError(
                f"git pull --rebase 실패 (충돌 가능, 발송 차단): {stderr}"
            ) from e

    def commit_and_push(self, newsletter_type: str, date_str: str) -> dict:
        """publish 직후 호출: ``data/`` 변경분을 add + commit + push.

        flag off / dry-run / 변경 없음인 경우 skipped 사유와 함께 반환.
        push는 실패해도 commit은 보존 (다음 실행에서 재전송).

        반환: {
            "committed": bool,
            "pushed": bool,
            "skipped": "disabled"|"dry-run"|"no-changes"|"no-remote"
                       |"add-failed"|"commit-failed"|"push-failed"|None,
        }
        """
        if not self.enabled:
            return {"committed": False, "pushed": False, "skipped": "disabled"}
        if self.dry_run:
            logger.info(
                "[dry-run] git add %s; commit -m 'auto: %s %s'; push origin",
                " ".join(self.paths), date_str, newsletter_type,
            )
            return {"committed": False, "pushed": False, "skipped": "dry-run"}

        # 실제 존재하는 경로만 add (data/db이 아직 생성 안 된 신규 클론 케이스 보호).
        existing = [p for p in self.paths if (self.repo_dir / p).exists()]
        if not existing:
            logger.info("git_sync: add 대상 경로 없음 (%s) — skip", list(self.paths))
            return {"committed": False, "pushed": False, "skipped": "no-paths"}
        try:
            self._run(["add", "--", *existing])
        except subprocess.CalledProcessError as e:
            logger.warning("git_sync.add 실패: %s", (e.stderr or "").strip())
            return {"committed": False, "pushed": False, "skipped": "add-failed"}

        diff = self._run(["diff", "--cached", "--name-only"], check=False)
        if not diff.stdout.strip():
            logger.info("git_sync: data/ 변경 없음 — commit skip")
            return {"committed": False, "pushed": False, "skipped": "no-changes"}

        msg = f"auto: {date_str} {newsletter_type}"
        try:
            self._run(["commit", "-m", msg])
            logger.info("git_sync.commit: %s", msg)
        except subprocess.CalledProcessError as e:
            logger.warning("git_sync.commit 실패: %s", (e.stderr or "").strip())
            return {"committed": False, "pushed": False, "skipped": "commit-failed"}

        if not self._has_remote():
            logger.info("git_sync.push: origin remote 없음 — local commit만 완료")
            return {"committed": True, "pushed": False, "skipped": "no-remote"}

        try:
            self._run(["push", "origin"])
            logger.info("git_sync.push: 성공")
            return {"committed": True, "pushed": True, "skipped": None}
        except subprocess.CalledProcessError as e:
            logger.warning(
                "git_sync.push 실패 (다음 실행에 재시도): %s",
                (e.stderr or "").strip(),
            )
            return {"committed": True, "pushed": False, "skipped": "push-failed"}
