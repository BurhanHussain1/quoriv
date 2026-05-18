"""Tests for ``quoriv.ui.themes`` — Phase 3 Slice 8.

The theme layer is a thin adapter over Rich. We verify:
  * The palette map exposes the names the schema accepts.
  * ``auto`` resolves to ``light`` / ``dark`` based on
    ``$COLORFGBG`` parsing, with sane fallbacks.
  * ``make_console`` returns a real :class:`rich.console.Console`
    whose ``theme`` attribute reflects the chosen palette.
"""

from __future__ import annotations

import pytest
from rich.console import Console
from rich.theme import Theme

from quoriv.ui.themes import (
    RICH_THEMES,
    _looks_like_light_background,
    make_console,
    resolve_theme,
)

# ---------------------------------------------------------------------------
# Palette map
# ---------------------------------------------------------------------------


class TestPaletteMap:
    def test_dark_is_explicit_none(self) -> None:
        # ``None`` means "use Rich defaults" — encoded explicitly so
        # ``make_console`` doesn't need a special-case branch.
        assert "dark" in RICH_THEMES
        assert RICH_THEMES["dark"] is None

    def test_light_is_a_rich_theme(self) -> None:
        assert isinstance(RICH_THEMES["light"], Theme)


# ---------------------------------------------------------------------------
# ``$COLORFGBG`` parsing
# ---------------------------------------------------------------------------


class TestLightBackgroundDetection:
    def test_no_env_var_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        assert _looks_like_light_background() is False

    @pytest.mark.parametrize("bg", ["7", "15"])
    def test_light_bg_indices_detected(self, bg: str, monkeypatch: pytest.MonkeyPatch) -> None:
        # Foreground / background; we only consult the last field.
        monkeypatch.setenv("COLORFGBG", f"0;{bg}")
        assert _looks_like_light_background() is True

    @pytest.mark.parametrize("bg", ["0", "8", "1"])
    def test_dark_bg_indices_not_detected_as_light(
        self, bg: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COLORFGBG", f"15;{bg}")
        assert _looks_like_light_background() is False

    def test_malformed_value_falls_through_to_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "not;a;number")
        assert _looks_like_light_background() is False

    def test_single_field_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Variable is set but doesn't have the ``fg;bg`` shape — we
        # have no signal, so don't claim a light background.
        monkeypatch.setenv("COLORFGBG", "15")
        assert _looks_like_light_background() is False


# ---------------------------------------------------------------------------
# resolve_theme
# ---------------------------------------------------------------------------


class TestResolveTheme:
    def test_dark_returns_dark(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        assert resolve_theme("dark") == "dark"

    def test_light_returns_light(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        assert resolve_theme("light") == "light"

    def test_auto_resolves_to_light_with_light_bg(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COLORFGBG", "0;15")
        assert resolve_theme("auto") == "light"

    def test_auto_resolves_to_dark_when_no_signal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        assert resolve_theme("auto") == "dark"


# ---------------------------------------------------------------------------
# make_console
# ---------------------------------------------------------------------------


class TestMakeConsole:
    def test_dark_returns_plain_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        console = make_console("dark")
        assert isinstance(console, Console)

    def test_light_console_carries_palette(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        console = make_console("light")
        assert isinstance(console, Console)
        # The light theme tweaks the ``dim`` style; verify that
        # change made it to the resolved console rather than the
        # Rich default.
        rendered = console.get_style("dim")
        # ``grey39`` is the light-theme override; ``rendered`` here
        # is a ``Style`` object whose ``color`` carries the name.
        assert rendered.color is not None
        assert "grey" in rendered.color.name.lower()

    def test_auto_falls_through_to_dark_without_signal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("COLORFGBG", raising=False)
        console = make_console("auto")
        assert isinstance(console, Console)

    def test_kwargs_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # ``force_terminal=False`` is a common test fixture pattern;
        # the factory must preserve callers' kwargs.
        monkeypatch.delenv("COLORFGBG", raising=False)
        console = make_console("dark", force_terminal=False)
        assert console.is_terminal is False

    def test_unknown_theme_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A typo in user config shouldn't break rendering — we fall
        # back to the Rich default palette silently. Verified by
        # building cleanly and returning a Console.
        monkeypatch.delenv("COLORFGBG", raising=False)
        console = make_console("nonsense-name")
        assert isinstance(console, Console)
