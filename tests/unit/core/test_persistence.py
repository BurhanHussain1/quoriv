"""Tests for `quoriv.core.persistence`."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from quoriv.core.persistence import (
    QUORIV_DIRNAME,
    SESSIONS_DB_NAME,
    SESSIONS_REGISTRY_NAME,
    NamedSession,
    SessionRegistry,
    db_path,
    ensure_quoriv_dir,
    quoriv_dir,
    registry_path,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


class TestPathHelpers:
    def test_quoriv_dir(self, tmp_path: Path) -> None:
        assert quoriv_dir(tmp_path) == tmp_path / QUORIV_DIRNAME

    def test_db_path(self, tmp_path: Path) -> None:
        assert db_path(tmp_path) == tmp_path / QUORIV_DIRNAME / SESSIONS_DB_NAME

    def test_registry_path(self, tmp_path: Path) -> None:
        assert registry_path(tmp_path) == (tmp_path / QUORIV_DIRNAME / SESSIONS_REGISTRY_NAME)

    def test_ensure_quoriv_dir_creates(self, tmp_path: Path) -> None:
        target = ensure_quoriv_dir(tmp_path)
        assert target.is_dir()
        assert target == tmp_path / QUORIV_DIRNAME

    def test_ensure_quoriv_dir_is_idempotent(self, tmp_path: Path) -> None:
        ensure_quoriv_dir(tmp_path)
        # Calling again should not raise and should leave the dir in place.
        target = ensure_quoriv_dir(tmp_path)
        assert target.is_dir()


# ---------------------------------------------------------------------------
# SessionRegistry: construction
# ---------------------------------------------------------------------------


class TestSessionRegistryConstruction:
    def test_for_cwd_uses_canonical_path(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        assert registry.path == registry_path(tmp_path)

    def test_missing_file_loads_as_empty(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        assert registry.list_named() == []
        assert registry.most_recent() is None
        assert registry.load("anything") is None

    def test_does_not_create_file_on_construction(self, tmp_path: Path) -> None:
        SessionRegistry.for_cwd(tmp_path)
        assert not registry_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# SessionRegistry: save / load / list
# ---------------------------------------------------------------------------


class TestSessionRegistrySaveLoad:
    def test_save_returns_record(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        record = registry.save("feature-x", "abc12345")
        assert isinstance(record, NamedSession)
        assert record.name == "feature-x"
        assert record.thread_id == "abc12345"
        assert record.saved_at  # non-empty ISO timestamp

    def test_save_persists_to_disk(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("feature-x", "abc12345")
        assert registry.path.exists()

    def test_save_round_trips_through_a_fresh_registry(self, tmp_path: Path) -> None:
        SessionRegistry.for_cwd(tmp_path).save("x", "tid-1")
        # New registry instance reads from disk.
        reopened = SessionRegistry.for_cwd(tmp_path)
        loaded = reopened.load("x")
        assert loaded is not None
        assert loaded.thread_id == "tid-1"

    def test_save_overwrites_existing_name(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("x", "tid-1")
        registry.save("x", "tid-2")
        record = registry.load("x")
        assert record is not None
        assert record.thread_id == "tid-2"
        # And only one entry with that name remains.
        names = [s.name for s in registry.list_named()]
        assert names.count("x") == 1

    def test_save_with_explicit_timestamp(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        fixed = datetime(2026, 5, 15, 10, 0, 0, tzinfo=UTC)
        record = registry.save("x", "tid", now=fixed)
        assert record.saved_at == "2026-05-15T10:00:00+00:00"

    def test_save_empty_name_raises(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        with pytest.raises(ValueError, match="non-empty"):
            registry.save("", "tid")

    def test_load_unknown_name_returns_none(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("x", "tid")
        assert registry.load("nope") is None

    def test_list_named_in_save_order(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("a", "t1", now=datetime(2026, 1, 1, tzinfo=UTC))
        registry.save("b", "t2", now=datetime(2026, 1, 2, tzinfo=UTC))
        registry.save("c", "t3", now=datetime(2026, 1, 3, tzinfo=UTC))
        names = [s.name for s in registry.list_named()]
        assert names == ["a", "b", "c"]

    def test_most_recent_by_saved_at(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("a", "t1", now=datetime(2026, 1, 1, tzinfo=UTC))
        registry.save("b", "t2", now=datetime(2026, 1, 3, tzinfo=UTC))
        registry.save("c", "t3", now=datetime(2026, 1, 2, tzinfo=UTC))
        most_recent = registry.most_recent()
        assert most_recent is not None
        assert most_recent.name == "b"

    def test_most_recent_empty(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        assert registry.most_recent() is None


# ---------------------------------------------------------------------------
# SessionRegistry: remove
# ---------------------------------------------------------------------------


class TestSessionRegistryRemove:
    def test_remove_existing(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("x", "tid")
        assert registry.remove("x") is True
        assert registry.load("x") is None

    def test_remove_unknown_returns_false(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        assert registry.remove("x") is False

    def test_remove_persists(self, tmp_path: Path) -> None:
        registry = SessionRegistry.for_cwd(tmp_path)
        registry.save("x", "tid")
        registry.remove("x")
        reopened = SessionRegistry.for_cwd(tmp_path)
        assert reopened.load("x") is None


# ---------------------------------------------------------------------------
# SessionRegistry: malformed-file recovery
# ---------------------------------------------------------------------------


class TestSessionRegistryMalformedRecovery:
    def test_malformed_json_resets_to_empty(self, tmp_path: Path) -> None:
        path = registry_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("not json at all {{{", encoding="utf-8")
        registry = SessionRegistry.for_cwd(tmp_path)
        assert registry.list_named() == []
        # And a new save replaces the corrupt file with valid content.
        registry.save("x", "tid")
        assert registry.load("x") is not None

    def test_non_dict_root_resets_to_empty(self, tmp_path: Path) -> None:
        path = registry_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text("[1, 2, 3]", encoding="utf-8")
        assert SessionRegistry.for_cwd(tmp_path).list_named() == []

    def test_missing_sessions_key(self, tmp_path: Path) -> None:
        path = registry_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text('{"version": 1}', encoding="utf-8")
        assert SessionRegistry.for_cwd(tmp_path).list_named() == []

    def test_non_list_sessions_value(self, tmp_path: Path) -> None:
        path = registry_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text('{"sessions": "oops"}', encoding="utf-8")
        assert SessionRegistry.for_cwd(tmp_path).list_named() == []

    def test_session_entries_with_missing_fields_are_dropped(self, tmp_path: Path) -> None:
        path = registry_path(tmp_path)
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"sessions": ['
            '{"name": "ok", "thread_id": "t", "saved_at": "2026-01-01"},'
            '{"name": "missing_id", "saved_at": "2026-01-01"},'
            '{"thread_id": "t", "saved_at": "2026-01-01"},'
            '"not an object",'
            '{"name": 1, "thread_id": "t", "saved_at": "2026-01-01"}'
            "]}",
            encoding="utf-8",
        )
        names = [s.name for s in SessionRegistry.for_cwd(tmp_path).list_named()]
        assert names == ["ok"]
