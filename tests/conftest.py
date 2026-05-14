"""Shared pytest fixtures for the Quoriv test suite."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import keyring
import keyring.errors
import pytest

from quoriv.config.keychain import PROVIDER_ENV_VARS

if TYPE_CHECKING:
    from collections.abc import Iterator


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


@pytest.fixture
def fake_keyring(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[tuple[str, str], str]]:
    """In-memory replacement for the OS keyring.

    Yields the backing store as a ``{(service, username): password}`` dict
    so tests can assert on it directly. All :mod:`keyring` calls are routed
    to this store for the duration of the test.

    Also clears every Quoriv-recognized provider env var so each test sees
    a deterministic environment (no leaking ``OPENAI_API_KEY`` etc. from
    the host shell).
    """
    for env_var in PROVIDER_ENV_VARS.values():
        monkeypatch.delenv(env_var, raising=False)

    store: dict[tuple[str, str], str] = {}

    def fake_get(service: str, username: str) -> str | None:
        return store.get((service, username))

    def fake_set(service: str, username: str, password: str) -> None:
        store[(service, username)] = password

    def fake_delete(service: str, username: str) -> None:
        if (service, username) not in store:
            raise keyring.errors.PasswordDeleteError("not found")
        del store[(service, username)]

    monkeypatch.setattr(keyring, "get_password", fake_get)
    monkeypatch.setattr(keyring, "set_password", fake_set)
    monkeypatch.setattr(keyring, "delete_password", fake_delete)

    yield store
