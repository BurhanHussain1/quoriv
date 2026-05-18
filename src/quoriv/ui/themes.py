"""UI theme palettes — Phase 3 Slice 8.

Quoriv ships three named themes via :class:`quoriv.config.schema.UIConfig`:

    ``dark``    Default. Tuned for dark terminal backgrounds — the
                Rich defaults already work well here so the palette
                is intentionally minimal.
    ``light``   Tuned for light terminal backgrounds. Swaps the
                ``dim`` style (default low-contrast white on dark)
                for a darker grey that stays readable on a white
                background, and shifts panel borders to a darker hue.
    ``auto``    Detect from ``$COLORFGBG`` (set by xterm-family
                terminals and many tmux configs) and fall through to
                ``dark`` when detection is inconclusive.

The themes only customise the few Rich style names that visibly
break on a wrong-background terminal — ``dim`` and panel borders.
Inline color tags (``[green]ok[/green]``, ``[red]err[/red]``) keep
their literal Rich-default rendering across themes because their
contrast holds on both backgrounds.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from rich.console import Console
from rich.theme import Theme

if TYPE_CHECKING:
    from quoriv.config.schema import Theme as ThemeName


# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------


_DARK_THEME = Theme(
    {
        # Empty overrides → Rich defaults apply. Kept as a named entry
        # so the factory can return ``None`` for the "do nothing" case
        # without special-casing the dark path.
    }
)


_LIGHT_THEME = Theme(
    {
        # On a light terminal the default ``dim`` (low-contrast grey
        # on dark) becomes near-invisible. Swap to a darker grey that
        # holds contrast on white.
        "dim": "grey39",
        # Panel borders default to cyan in Quoriv; cyan on a light
        # background can wash out. A slightly darker blue keeps the
        # frame visible.
        "panel.border": "blue",
    }
)


RICH_THEMES: dict[str, Theme | None] = {
    "dark": None,  # use Rich defaults
    "light": _LIGHT_THEME,
}
"""Named palettes the :func:`make_console` factory understands.

``None`` means "no theme override" — equivalent to passing nothing
to ``Console()``. The ``auto`` token is resolved by
:func:`resolve_theme` before this map is consulted, so it never
appears as a key here.
"""


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------


def _looks_like_light_background() -> bool:
    """Return ``True`` if the terminal is probably set to a light background.

    Uses ``$COLORFGBG`` — an xterm-family convention of the form
    ``"<fg>;<bg>"`` where ``<bg>`` is an ANSI color index. Indexes
    7 (light grey) and 15 (white) are the standard "light background"
    values. Any other value (or a missing variable) means we can't
    tell, so we return ``False`` and let the caller fall back to the
    dark default.
    """
    raw = os.environ.get("COLORFGBG")
    if not raw:
        return False
    parts = raw.split(";")
    if len(parts) < 2:
        return False
    try:
        bg = int(parts[-1])
    except ValueError:
        return False
    return bg in {7, 15}


def resolve_theme(theme: ThemeName | str) -> str:
    """Turn a config theme token into one of the concrete names.

    ``auto`` resolves to ``light`` when ``$COLORFGBG`` indicates a
    light background, otherwise ``dark``. Any other value is
    returned unchanged (callers may pass a custom name in the
    future).
    """
    if theme == "auto":
        return "light" if _looks_like_light_background() else "dark"
    return theme


def make_console(theme: ThemeName | str = "auto", **kwargs: object) -> Console:
    """Construct a :class:`rich.console.Console` for the chosen theme.

    Args:
        theme: ``dark`` / ``light`` / ``auto`` (or any name returned
            by ``resolve_theme``). Unknown names fall back to the
            default Rich palette so a typo doesn't break rendering.
        **kwargs: Forwarded to ``Console()`` so callers can still
            pass ``file=``, ``force_terminal=``, etc.

    Returns:
        A configured ``Console``. With the dark/auto-resolved-dark
        path the result is indistinguishable from ``Console()``.
    """
    resolved = resolve_theme(theme)
    palette = RICH_THEMES.get(resolved)
    if palette is None:
        return Console(**kwargs)  # type: ignore[arg-type]
    return Console(theme=palette, **kwargs)  # type: ignore[arg-type]
