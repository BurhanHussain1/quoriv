"""Make ``python -m quoriv`` work the same as the ``quoriv`` console script.

Both entry points dispatch to the same Typer app.
"""

from __future__ import annotations

from quoriv.cli import app

if __name__ == "__main__":
    app()
