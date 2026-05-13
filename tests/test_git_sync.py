"""tests/test_git_sync.py — git_sync 모듈 단위 테스트.

subprocess.run을 mock해 git 명령 호출 시퀀스와 분기를 검증.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.git_sync import GitSync, GitSyncError, DEFAULT_SYNC_PATHS


@pytest.fixture
def repo_dir(tmp_path):
    # 기본 동기화 대상 경로를 미리 생성해 add 단계에서 누락되지 않도록.
    (tmp_path / "data" / "newsletters").mkdir(parents=True)
    (tmp_path / "data" / "db").mkdir(parents=True)
    return tmp_path


def _ok(stdout: str = "", stderr: str = "") -> MagicMock:
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.stdout = stdout
    m.stderr = stderr
    m.returncode = 0
    return m


def _fail(stderr: str = "boom") -> subprocess.CalledProcessError:
    return subprocess.CalledProcessError(1, ["git"], output="", stderr=stderr)


# ── 초기화 ──


class TestInit:
    def test_disabled_by_default(self, repo_dir):
        s = GitSync(repo_dir)
        assert s.enabled is False
        assert s.dry_run is False
        assert s.paths == DEFAULT_SYNC_PATHS

    def test_enabled_flag(self, repo_dir):
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        assert s.enabled is True

    def test_dry_run_flag(self, repo_dir):
        s = GitSync(repo_dir, {"features": {
            "git_autosync": True, "git_autosync_dry_run": True,
        }})
        assert s.dry_run is True

    def test_custom_paths(self, repo_dir):
        s = GitSync(repo_dir, paths=["foo", "bar"])
        assert s.paths == ("foo", "bar")


# ── pull_or_fail ──


class TestPullOrFail:
    def test_disabled_noop(self, repo_dir):
        s = GitSync(repo_dir)  # not enabled
        with patch("src.git_sync.subprocess.run") as run:
            result = s.pull_or_fail()
        assert result == {"action": "skipped", "reason": "disabled"}
        run.assert_not_called()

    def test_dry_run_noop(self, repo_dir):
        s = GitSync(repo_dir, {"features": {
            "git_autosync": True, "git_autosync_dry_run": True,
        }})
        with patch("src.git_sync.subprocess.run") as run:
            run.return_value = _ok()  # remote check
            result = s.pull_or_fail()
        assert result == {"action": "skipped", "reason": "dry-run"}
        # remote 확인만 호출되어야 함 (pull은 호출 X)
        called_args = [c.args[0] for c in run.call_args_list]
        assert all("pull" not in args for args in called_args)

    def test_no_remote_skip(self, repo_dir):
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            # remote get-url 실패 → CalledProcessError
            run.side_effect = _fail("no such remote")
            result = s.pull_or_fail()
        assert result == {"action": "skipped", "reason": "no-remote"}

    def test_pull_success(self, repo_dir):
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            run.side_effect = [_ok("git@github.com:x/y"), _ok("Already up to date.")]
            result = s.pull_or_fail()
        assert result == {"action": "pulled", "reason": None}
        # 2번 호출: remote get-url + pull
        assert run.call_count == 2
        assert "pull" in run.call_args_list[1].args[0]

    def test_pull_rebase_conflict_raises(self, repo_dir):
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        calls = []

        def side(cmd, **kw):
            calls.append(cmd)
            if "remote" in cmd:
                return _ok("origin")
            if "pull" in cmd:
                raise _fail("CONFLICT (content)")
            if "rebase" in cmd and "--abort" in cmd:
                return _ok()
            raise AssertionError(f"unexpected call {cmd}")

        with patch("src.git_sync.subprocess.run", side_effect=side):
            with pytest.raises(GitSyncError, match="rebase"):
                s.pull_or_fail()
        # rebase --abort가 호출됐는지 확인
        assert any("--abort" in c for c in calls)


# ── commit_and_push ──


class TestCommitAndPush:
    def test_disabled_noop(self, repo_dir):
        s = GitSync(repo_dir)
        with patch("src.git_sync.subprocess.run") as run:
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": False, "pushed": False, "skipped": "disabled"}
        run.assert_not_called()

    def test_dry_run_noop(self, repo_dir):
        s = GitSync(repo_dir, {"features": {
            "git_autosync": True, "git_autosync_dry_run": True,
        }})
        with patch("src.git_sync.subprocess.run") as run:
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": False, "pushed": False, "skipped": "dry-run"}
        run.assert_not_called()

    def test_no_changes(self, repo_dir):
        """add 후 staged diff가 비어있으면 commit skip."""
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            run.side_effect = [_ok(), _ok(stdout="")]  # add, diff (empty)
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": False, "pushed": False, "skipped": "no-changes"}

    def test_add_failed(self, repo_dir):
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            run.side_effect = _fail("pathspec did not match")
            result = s.commit_and_push("daily", "2026-05-13")
        assert result["skipped"] == "add-failed"
        assert result["committed"] is False

    def test_no_paths_exist(self, tmp_path):
        """data/ 서브디렉토리가 모두 없으면 add를 시도하지 않고 skip."""
        s = GitSync(tmp_path, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": False, "pushed": False, "skipped": "no-paths"}
        run.assert_not_called()

    def test_commit_only_no_remote(self, repo_dir):
        """변경 있고 commit 성공 + remote 없음 → committed=True, pushed=False."""
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            run.side_effect = [
                _ok(),                              # add
                _ok(stdout="data/db/x.csv\n"),     # diff (changes)
                _ok(),                              # commit
                _fail("no such remote"),           # remote get-url
            ]
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": True, "pushed": False, "skipped": "no-remote"}

    def test_full_success(self, repo_dir):
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        calls = []

        def side(cmd, **kw):
            calls.append(cmd)
            if "add" in cmd:
                return _ok()
            if "diff" in cmd:
                return _ok(stdout="data/newsletters/daily_2026-05-13.md\n")
            if "commit" in cmd:
                # commit message 검증
                assert "-m" in cmd
                msg_idx = cmd.index("-m") + 1
                assert cmd[msg_idx] == "auto: 2026-05-13 daily"
                return _ok()
            if "remote" in cmd:
                return _ok(stdout="origin url")
            if "push" in cmd:
                return _ok()
            raise AssertionError(f"unexpected {cmd}")

        with patch("src.git_sync.subprocess.run", side_effect=side):
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": True, "pushed": True, "skipped": None}

    def test_push_failed_commit_preserved(self, repo_dir):
        """push 실패 시 committed=True (warn만, 다음 실행에서 재시도)."""
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            run.side_effect = [
                _ok(),                                  # add
                _ok(stdout="data/db/x.csv\n"),         # diff
                _ok(),                                  # commit
                _ok(),                                  # remote get-url
                _fail("rejected — non-fast-forward"),  # push
            ]
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": True, "pushed": False, "skipped": "push-failed"}

    def test_commit_failed(self, repo_dir):
        """commit 단계 실패 (drive 등)."""
        s = GitSync(repo_dir, {"features": {"git_autosync": True}})
        with patch("src.git_sync.subprocess.run") as run:
            run.side_effect = [
                _ok(),                                  # add
                _ok(stdout="data/db/x.csv\n"),         # diff
                _fail("hook rejected"),                # commit
            ]
            result = s.commit_and_push("daily", "2026-05-13")
        assert result == {"committed": False, "pushed": False, "skipped": "commit-failed"}


# ── 실제 git CLI 사용 (smoke test) ──


class TestIntegrationSmoke:
    """실제 git CLI를 사용한 smoke 테스트 (가짜 repo 생성)."""

    def test_real_repo_commit(self, tmp_path):
        """tmp_path에 진짜 git repo를 초기화하고 commit_and_push이 동작하는지."""
        # 가짜 repo
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email",
                        "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name",
                        "Test User"], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "commit.gpgsign",
                        "false"], check=True)

        # data 디렉토리 + 파일 생성
        data_dir = tmp_path / "data" / "newsletters"
        data_dir.mkdir(parents=True)
        (data_dir / "daily_test.md").write_text("hello", encoding="utf-8")

        s = GitSync(tmp_path, {"features": {"git_autosync": True}})
        result = s.commit_and_push("daily", "2026-05-13")

        # remote 없음 → no-remote, committed=True
        assert result["committed"] is True
        assert result["pushed"] is False
        assert result["skipped"] == "no-remote"

        # 실제로 commit이 들어갔는지 확인
        log = subprocess.run(
            ["git", "-C", str(tmp_path), "log", "--oneline"],
            capture_output=True, text=True, check=True,
        )
        assert "auto: 2026-05-13 daily" in log.stdout
