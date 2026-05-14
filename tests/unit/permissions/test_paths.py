"""Tests for `quoriv.permissions.paths`."""

from __future__ import annotations

from deepagents import FilesystemPermission

from quoriv.permissions.paths import PATH_PROTECTION


class TestPathProtection:
    def test_all_entries_are_filesystem_permissions(self) -> None:
        assert all(isinstance(rule, FilesystemPermission) for rule in PATH_PROTECTION)

    def test_all_entries_are_deny(self) -> None:
        assert all(rule.mode == "deny" for rule in PATH_PROTECTION)

    def test_env_files_write_blocked(self) -> None:
        paths = {p for rule in PATH_PROTECTION for p in rule.paths}
        assert "/.env" in paths
        assert "/.env.*" in paths

    def test_git_directory_write_blocked(self) -> None:
        paths = {p for rule in PATH_PROTECTION for p in rule.paths}
        assert "/.git/**" in paths

    def test_ssh_directory_read_and_write_blocked(self) -> None:
        ssh_rules = [r for r in PATH_PROTECTION if "/.ssh/**" in r.paths]
        assert ssh_rules, "expected at least one rule covering /.ssh/**"
        ops = {op for rule in ssh_rules for op in rule.operations}
        assert "read" in ops
        assert "write" in ops

    def test_secrets_directory_read_and_write_blocked(self) -> None:
        secret_rules = [r for r in PATH_PROTECTION if "/secrets/**" in r.paths]
        assert secret_rules, "expected at least one rule covering /secrets/**"
        ops = {op for rule in secret_rules for op in rule.operations}
        assert "read" in ops
        assert "write" in ops

    def test_paths_are_posix_rooted(self) -> None:
        for rule in PATH_PROTECTION:
            for path in rule.paths:
                assert path.startswith("/"), f"path must start with '/': {path!r}"

    def test_constant_is_tuple(self) -> None:
        # Mutability would let callers accidentally extend the policy at
        # runtime. Keep it locked to a tuple.
        assert isinstance(PATH_PROTECTION, tuple)
