"""Shared pytest fixtures for the Quoriv test suite."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ``Path.home()`` to a temp directory for the test.

    Also sets ``HOME`` and ``USERPROFILE`` env vars so anything that reads
    them directly (rather than via ``Path.home``) sees the same fake home.

    Yields the fake home directory, already created and empty.
    """
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))  # Windows
    monkeypatch.setattr(Path, "home", lambda: home)
    return home
