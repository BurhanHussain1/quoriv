"""Static validation for the MkDocs site + Pages deploy workflow — Phase 4 Slice 4.

The docs site only builds in CI, and mkdocs-material's strict mode
rejects broken nav references at build time. These tests catch a
broader class of regressions earlier (missing nav entry, missing
include-markdown plugin, deploy workflow drift) before the CI run
that ships the site to GitHub Pages.

We parse the YAML with ``yaml.unsafe_load`` here because mkdocs.yml
uses ``!!python/name:...`` tags for pymdownx emoji extensions —
``safe_load`` raises on those. The file is checked into the repo and
not user-supplied, so the unsafe loader is fine.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MKDOCS_PATH = REPO_ROOT / "mkdocs.yml"
DOCS_DIR = REPO_ROOT / "docs"
DOCS_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "docs.yml"


class _StubTagsLoader(yaml.SafeLoader):
    """SafeLoader that returns ``!!python/name:...`` tags as the bare path string.

    mkdocs-material registers emoji-generator constructors that require
    ``material.extensions.emoji`` at import time; ``yaml.unsafe_load``
    therefore fails outside a docs-extras install. We don't need to
    invoke those callables here — we only need to read the config —
    so swapping them for an inert string keeps the test self-contained.
    """


def _construct_python_name_stub(_loader: yaml.Loader, suffix: str, _node: yaml.Node) -> str:
    return suffix


_StubTagsLoader.add_multi_constructor("tag:yaml.org,2002:python/name:", _construct_python_name_stub)


@pytest.fixture(scope="module")
def mkdocs_config() -> dict[str, Any]:
    """Parse ``mkdocs.yml`` once per module."""
    raw = MKDOCS_PATH.read_text(encoding="utf-8")
    parsed = yaml.load(raw, Loader=_StubTagsLoader)
    assert isinstance(parsed, dict), "mkdocs.yml did not parse to a mapping"
    return parsed


@pytest.fixture(scope="module")
def docs_workflow() -> dict[str, Any]:
    """Parse ``.github/workflows/docs.yml`` once per module."""
    raw = DOCS_WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict), "docs.yml did not parse to a mapping"
    return parsed


def _trigger_section(workflow: dict[str, Any]) -> dict[str, Any]:
    """Workaround PyYAML mapping the bare key ``on`` to ``True``."""
    return workflow.get("on") or workflow.get(True)  # type: ignore[return-value]


def _nav_pages(nav: list[Any]) -> dict[str, str]:
    """Flatten the nav list into a ``{title: path}`` dict.

    Sections (dicts with a nested list) are skipped — the slice only
    ships a flat nav.
    """
    flat: dict[str, str] = {}
    for entry in nav:
        if isinstance(entry, dict):
            for title, target in entry.items():
                if isinstance(target, str):
                    flat[title] = target
    return flat


class TestMkdocsConfig:
    def test_mkdocs_yml_exists(self) -> None:
        assert MKDOCS_PATH.is_file(), f"missing {MKDOCS_PATH}"

    def test_site_name_set(self, mkdocs_config: dict[str, Any]) -> None:
        assert mkdocs_config.get("site_name") == "Quoriv"

    def test_repo_url_points_at_github(self, mkdocs_config: dict[str, Any]) -> None:
        # edit_uri + repo_url power the "Edit this page" affordance — getting
        # them right means contributors land on the actual source file.
        assert "github.com/BurhanHussain1/quoriv" in mkdocs_config.get("repo_url", "")
        assert mkdocs_config.get("edit_uri", "").startswith("edit/main/docs")

    def test_uses_material_theme(self, mkdocs_config: dict[str, Any]) -> None:
        theme = mkdocs_config.get("theme")
        if isinstance(theme, str):
            assert theme == "material"
        else:
            assert theme.get("name") == "material"

    def test_include_markdown_plugin_enabled(self, mkdocs_config: dict[str, Any]) -> None:
        # Required for docs/*.md to pull in the root README / CHANGELOG /
        # CONTRIBUTING / SECURITY / PROJECT_PLAN without duplicating them.
        plugins = mkdocs_config.get("plugins", [])
        plugin_names = [p if isinstance(p, str) else next(iter(p)) for p in plugins]
        assert "include-markdown" in plugin_names

    def test_search_plugin_enabled(self, mkdocs_config: dict[str, Any]) -> None:
        plugins = mkdocs_config.get("plugins", [])
        plugin_names = [p if isinstance(p, str) else next(iter(p)) for p in plugins]
        assert "search" in plugin_names


class TestNavStructure:
    def test_nav_present(self, mkdocs_config: dict[str, Any]) -> None:
        assert mkdocs_config.get("nav"), "mkdocs.yml is missing a nav section"

    def test_nav_includes_core_pages(self, mkdocs_config: dict[str, Any]) -> None:
        pages = _nav_pages(mkdocs_config["nav"])
        # The five core pages — anything more is optional polish.
        assert pages.get("Home") == "index.md"
        assert pages.get("Changelog") == "changelog.md"
        assert pages.get("Contributing") == "contributing.md"
        assert pages.get("Security") == "security.md"

    @pytest.mark.parametrize(
        "doc_file",
        [
            "index.md",
            "changelog.md",
            "contributing.md",
            "security.md",
            "architecture.md",
            "project-plan.md",
        ],
    )
    def test_nav_targets_exist(self, doc_file: str) -> None:
        # Every nav target must resolve to an actual file under docs/,
        # otherwise `mkdocs build --strict` fails the docs workflow.
        assert (DOCS_DIR / doc_file).is_file(), f"missing docs/{doc_file}"


class TestDocsWorkflow:
    def test_workflow_exists(self) -> None:
        assert DOCS_WORKFLOW_PATH.is_file()

    def test_triggers_on_main_push(self, docs_workflow: dict[str, Any]) -> None:
        triggers = _trigger_section(docs_workflow)
        push = triggers.get("push", {})
        assert "main" in push.get("branches", [])

    def test_supports_manual_dispatch(self, docs_workflow: dict[str, Any]) -> None:
        triggers = _trigger_section(docs_workflow)
        assert "workflow_dispatch" in triggers

    def test_has_pages_oidc_permissions(self, docs_workflow: dict[str, Any]) -> None:
        # `actions/deploy-pages` requires `pages: write` + `id-token: write`.
        # `contents: read` is implicit on workflow level so we still assert it.
        permissions = docs_workflow.get("permissions", {})
        assert permissions.get("pages") == "write"
        assert permissions.get("id-token") == "write"
        assert permissions.get("contents") == "read"

    def test_build_runs_mkdocs(self, docs_workflow: dict[str, Any]) -> None:
        # We don't enforce --strict yet — included root files (README,
        # CHANGELOG, …) carry pre-existing relative links MkDocs treats
        # as warnings. Just confirm the build step invokes `mkdocs build`.
        steps = docs_workflow["jobs"]["build"]["steps"]
        commands = " ".join(s.get("run", "") for s in steps if "run" in s)
        assert "mkdocs build" in commands

    def test_build_uploads_pages_artifact(self, docs_workflow: dict[str, Any]) -> None:
        steps = docs_workflow["jobs"]["build"]["steps"]
        uploads = [s for s in steps if "actions/upload-pages-artifact" in s.get("uses", "")]
        assert uploads, "build job must upload the rendered site via actions/upload-pages-artifact"

    def test_deploy_uses_actions_deploy_pages(self, docs_workflow: dict[str, Any]) -> None:
        steps = docs_workflow["jobs"]["deploy"]["steps"]
        deploys = [s for s in steps if "actions/deploy-pages" in s.get("uses", "")]
        assert deploys

    def test_deploy_gated_to_main(self, docs_workflow: dict[str, Any]) -> None:
        # Manual dispatches off a feature branch should build but not publish.
        condition = docs_workflow["jobs"]["deploy"].get("if", "")
        assert "main" in condition

    def test_deploy_targets_github_pages_environment(self, docs_workflow: dict[str, Any]) -> None:
        env = docs_workflow["jobs"]["deploy"].get("environment", {})
        if isinstance(env, str):
            assert env == "github-pages"
        else:
            assert env.get("name") == "github-pages"


class TestPyprojectDocsGroup:
    def test_include_markdown_plugin_in_docs_extra(self) -> None:
        # The docs/*.md shims reference {%-include-markdown-%} blocks; the
        # plugin must be installable from the `docs` extra so a `pip
        # install -e .[docs]` produces a working `mkdocs build`.
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        docs_extras = data["project"]["optional-dependencies"]["docs"]
        joined = " ".join(docs_extras)
        assert "mkdocs-include-markdown-plugin" in joined
        assert "mkdocs-material" in joined
