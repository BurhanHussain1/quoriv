"""Session persistence: SQLite checkpointer paths + named-session sidecar.

The DeepAgent's conversational state lives in a LangGraph checkpointer.
Phase 1 Slice 7 swaps the in-memory checkpointer for an
``AsyncSqliteSaver`` rooted at ``<cwd>/.quoriv/sessions.db`` so the
agent's working state survives across restarts.

That checkpointer keys threads by an opaque ``thread_id`` — restoring a
session means reusing the right ID. To make that ergonomic from the
chat loop, we keep a small **sidecar JSON file** at
``<cwd>/.quoriv/sessions.json`` mapping user-supplied names to
``thread_id`` values, plus a save timestamp::

    {
      "version": 1,
      "sessions": [
        {"name": "feature-x", "thread_id": "ab12...", "saved_at": "..."},
        ...
      ]
    }

:class:`SessionRegistry` is a thin, file-backed wrapper around that
sidecar. It is intentionally LangGraph-agnostic so it can be unit-tested
without touching SQLite — the registry maps **names**, while the
underlying ``AsyncSqliteSaver`` is the source of truth for the state
itself.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

QUORIV_DIRNAME = ".quoriv"
SESSIONS_DB_NAME = "sessions.db"
SESSIONS_REGISTRY_NAME = "sessions.json"
_REGISTRY_VERSION = 1


def quoriv_dir(cwd: Path) -> Path:
    """Return ``<cwd>/.quoriv``."""
    return cwd / QUORIV_DIRNAME


def db_path(cwd: Path) -> Path:
    """Return the SQLite checkpointer DB path for ``cwd``."""
    return quoriv_dir(cwd) / SESSIONS_DB_NAME


def registry_path(cwd: Path) -> Path:
    """Return the named-session sidecar JSON path for ``cwd``."""
    return quoriv_dir(cwd) / SESSIONS_REGISTRY_NAME


def ensure_quoriv_dir(cwd: Path) -> Path:
    """Create ``<cwd>/.quoriv/`` if missing and return it."""
    target = quoriv_dir(cwd)
    target.mkdir(parents=True, exist_ok=True)
    return target


@dataclass(frozen=True)
class NamedSession:
    """One named session record in the registry sidecar."""

    name: str
    thread_id: str
    saved_at: str  # ISO-8601 UTC timestamp


class SessionRegistry:
    """File-backed ``name → thread_id`` mapping under ``.quoriv/sessions.json``.

    The registry is loaded on construction and written eagerly on every
    mutation. Malformed or missing files reset to an empty registry
    rather than raising — the underlying SQLite DB is the real source of
    truth for state, so a corrupted name index is a recoverable
    convenience-layer issue, not a fatal one.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._sessions: list[NamedSession] = self._read()

    @classmethod
    def for_cwd(cls, cwd: Path) -> SessionRegistry:
        """Convenience: open the registry rooted at ``cwd``."""
        return cls(registry_path(cwd))

    @property
    def path(self) -> Path:
        """Filesystem path the registry persists to."""
        return self._path

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def save(
        self,
        name: str,
        thread_id: str,
        *,
        now: datetime | None = None,
    ) -> NamedSession:
        """Anchor ``thread_id`` under ``name``, overwriting any prior entry.

        Returns the freshly stored :class:`NamedSession`.

        Raises:
            ValueError: if ``name`` is empty.
        """
        if not name:
            raise ValueError("session name must be non-empty")
        timestamp = (now or datetime.now(tz=UTC)).isoformat()
        record = NamedSession(name=name, thread_id=thread_id, saved_at=timestamp)
        self._sessions = [s for s in self._sessions if s.name != name]
        self._sessions.append(record)
        self._write()
        return record

    def remove(self, name: str) -> bool:
        """Drop the session named ``name``.

        Returns:
            True if a record was removed, False if no such name existed.
        """
        before = len(self._sessions)
        self._sessions = [s for s in self._sessions if s.name != name]
        if len(self._sessions) != before:
            self._write()
            return True
        return False

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def load(self, name: str) -> NamedSession | None:
        """Return the session stored under ``name``, or ``None``."""
        for session in self._sessions:
            if session.name == name:
                return session
        return None

    def list_named(self) -> list[NamedSession]:
        """Return all named sessions in save order (oldest first)."""
        return list(self._sessions)

    def most_recent(self) -> NamedSession | None:
        """Return the most-recently-saved session, by ``saved_at``."""
        if not self._sessions:
            return None
        return max(self._sessions, key=lambda s: s.saved_at)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------

    def _read(self) -> list[NamedSession]:
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, dict):
            return []
        sessions = data.get("sessions")
        if not isinstance(sessions, list):
            return []
        result: list[NamedSession] = []
        for entry in sessions:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            thread_id = entry.get("thread_id")
            saved_at = entry.get("saved_at")
            if isinstance(name, str) and isinstance(thread_id, str) and isinstance(saved_at, str):
                result.append(NamedSession(name=name, thread_id=thread_id, saved_at=saved_at))
        return result

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": _REGISTRY_VERSION,
            "sessions": [
                {"name": s.name, "thread_id": s.thread_id, "saved_at": s.saved_at}
                for s in self._sessions
            ],
        }
        self._path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
