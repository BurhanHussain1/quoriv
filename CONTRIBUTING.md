# Contributing to Quoriv

Thank you for considering a contribution. Quoriv is built openly and we welcome bug reports, feature requests, documentation improvements, and code contributions.

---

## Code of conduct

Be kind. Disagree with ideas, not people. Assume good faith. We follow the [Contributor Covenant](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).

---

## Ways to contribute

- **Report a bug** — open an [issue](https://github.com/BurhanHussain1/quoriv/issues) with reproduction steps and environment info.
- **Request a feature** — open an issue tagged `enhancement`. Describe the use case, not just the feature.
- **Improve docs** — even fixing a typo helps. Submit a PR.
- **Submit code** — see the workflow below.

---

## Development setup

Quoriv requires **Python 3.11+**.

```bash
# Clone
git clone https://github.com/BurhanHussain1/quoriv.git
cd quoriv

# Install with dev + AST extras
pip install -e ".[dev,ast]"

# Install git hooks
pre-commit install
```

---

## Workflow

1. **Find or open an issue** before starting significant work. This avoids wasted effort.
2. **Fork the repo** and create a feature branch from `main`:
   ```bash
   git checkout -b feature/short-description
   ```
3. **Make your changes**. Keep commits focused and descriptive.
4. **Run the checks locally** before pushing:
   ```bash
   ruff check .
   ruff format .
   mypy
   pytest
   ```
5. **Push and open a pull request** against `main`. The PR template will guide you.

---

## Coding standards

- **Style**: enforced by `ruff format` — don't fight the formatter.
- **Lint**: `ruff check` must pass. See `pyproject.toml` for the rule set.
- **Types**: full type annotations. `mypy --strict` must pass.
- **Tests**: every new feature or bug-fix gets a test. Tests live in `tests/`.
- **Docstrings**: only when non-obvious. Don't restate what the code says.
- **Commits**: imperative present-tense (`Add foo`, not `Added foo`). Reference issues like `Fix #42` to auto-close.

---

## Architectural rules

A few non-negotiables that keep the project coherent:

1. **The `core/` package must never import from `ui/` or `cli/`.** The agent runtime should be embeddable by any client.
2. **All tool calls go through `permissions/guard.py`.** Don't bypass the permission system.
3. **API keys never touch disk.** Use `keyring` exclusively.
4. **No global state.** Pass dependencies explicitly.
5. **Stream first.** UI rendering must work with partial / streaming output.

---

## Pull request checklist

- [ ] My branch is up to date with `main`
- [ ] `ruff check .` passes
- [ ] `ruff format .` produces no diff
- [ ] `mypy` passes
- [ ] `pytest` passes locally on Python 3.11 and 3.12
- [ ] I added tests for new behavior
- [ ] I updated `CHANGELOG.md` (under `Unreleased`)
- [ ] I updated docs if user-facing behavior changed

---

## Reporting security issues

**Do not file public issues for security vulnerabilities.** See [`SECURITY.md`](SECURITY.md) for the disclosure process.

---

## License

By contributing, you agree your contributions will be licensed under the [Apache 2.0 License](LICENSE).
