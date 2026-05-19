"""Static validation for ``.github/workflows/release.yml`` — Phase 4 Slice 3.

The release workflow itself only runs on tag push, so these tests are
the only mechanism that catches structural drift (a missing OIDC
permission, a renamed publish action, a broken trigger filter) before
a real release cuts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    """Parse the release workflow once per module."""
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict), "release.yml did not parse to a mapping"
    return parsed


def _trigger_section(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return the ``on:`` mapping.

    PyYAML maps the bare key ``on`` to Python ``True`` because YAML 1.1
    treats it as a boolean. Handle both keys so the test works with any
    PyYAML version.
    """
    # mypy is happy treating dict access as Any here — tests aren't typed-strict.
    return workflow.get("on") or workflow.get(True)  # type: ignore[return-value]


class TestWorkflowFile:
    def test_exists(self) -> None:
        assert WORKFLOW_PATH.is_file(), f"missing {WORKFLOW_PATH}"

    def test_parses_as_yaml(self, workflow: dict[str, Any]) -> None:
        # Reaching this assertion means yaml.safe_load returned a mapping.
        assert workflow["name"] == "release"


class TestTriggers:
    def test_runs_on_version_tag_push(self, workflow: dict[str, Any]) -> None:
        triggers = _trigger_section(workflow)
        push = triggers.get("push", {})
        tags = push.get("tags", [])
        assert "v*.*.*" in tags, f"workflow should trigger on v*.*.* tags, got tags={tags!r}"

    def test_supports_manual_dispatch(self, workflow: dict[str, Any]) -> None:
        # workflow_dispatch lets us smoke-test the build job without
        # pushing a tag — handy when bringing the pipeline up.
        triggers = _trigger_section(workflow)
        assert "workflow_dispatch" in triggers


class TestBuildJob:
    def test_build_job_exists(self, workflow: dict[str, Any]) -> None:
        assert "build" in workflow["jobs"]

    def test_build_uses_pypa_build(self, workflow: dict[str, Any]) -> None:
        # `python -m build` is the canonical PEP 517 frontend; the
        # backend (hatchling) is selected by pyproject.toml.
        steps = workflow["jobs"]["build"]["steps"]
        commands = " ".join(step.get("run", "") for step in steps if "run" in step)
        assert "python -m build" in commands

    def test_build_validates_with_twine_check(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["build"]["steps"]
        commands = " ".join(step.get("run", "") for step in steps if "run" in step)
        assert "twine check" in commands

    def test_build_verifies_tag_matches_pyproject_version(self, workflow: dict[str, Any]) -> None:
        # Cheap insurance: if someone tags v1.2.3 with pyproject still
        # pinned at 1.2.2, the release fails loud instead of publishing
        # the wrong artifact.
        steps = workflow["jobs"]["build"]["steps"]
        commands = " ".join(step.get("run", "") for step in steps if "run" in step)
        assert "pyproject" in commands.lower()
        assert "GITHUB_REF" in commands or "github.ref" in commands

    def test_build_uploads_dist_artifact(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["build"]["steps"]
        uploads = [step for step in steps if "actions/upload-artifact" in step.get("uses", "")]
        assert uploads, "build job should upload the dist/ artifact"
        assert uploads[0]["with"]["name"] == "dist"


class TestPublishJob:
    def test_publish_job_exists(self, workflow: dict[str, Any]) -> None:
        assert "publish" in workflow["jobs"]

    def test_publish_uses_oidc_trusted_publishing(self, workflow: dict[str, Any]) -> None:
        # OIDC trusted publishing is the recommended PyPI auth path —
        # no long-lived API token in repo secrets.
        permissions = workflow["jobs"]["publish"].get("permissions", {})
        assert permissions.get("id-token") == "write", (
            "publish job requires `id-token: write` for PyPI OIDC trusted publishing"
        )

    def test_publish_uses_pypa_action(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["publish"]["steps"]
        publish_steps = [s for s in steps if "pypa/gh-action-pypi-publish" in s.get("uses", "")]
        assert publish_steps, "publish job should use pypa/gh-action-pypi-publish"

    def test_publish_depends_on_build(self, workflow: dict[str, Any]) -> None:
        needs = workflow["jobs"]["publish"].get("needs")
        # `needs` may be a string or a list — accept either.
        if isinstance(needs, str):
            assert needs == "build"
        else:
            assert "build" in needs

    def test_publish_gated_to_tag_push(self, workflow: dict[str, Any]) -> None:
        # workflow_dispatch is allowed to build (for smoke tests) but
        # must NOT publish to PyPI without an explicit tag.
        condition = workflow["jobs"]["publish"].get("if", "")
        assert "tags/v" in condition
        assert "push" in condition

    def test_publish_targets_pypi_environment(self, workflow: dict[str, Any]) -> None:
        # GitHub deployment environment named `pypi` is the conventional
        # gate for trusted publishing — lets the repo owner add manual
        # approval before the publish step runs.
        env = workflow["jobs"]["publish"].get("environment")
        if isinstance(env, str):
            assert env == "pypi"
        else:
            assert env.get("name") == "pypi"


class TestGithubReleaseJob:
    def test_github_release_job_exists(self, workflow: dict[str, Any]) -> None:
        # Attaching the built wheel + sdist to the GitHub release page
        # gives users a direct download path independent of PyPI.
        assert "github-release" in workflow["jobs"]

    def test_github_release_uses_softprops_action(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["github-release"]["steps"]
        release_steps = [s for s in steps if "softprops/action-gh-release" in s.get("uses", "")]
        assert release_steps

    def test_github_release_has_contents_write_permission(self, workflow: dict[str, Any]) -> None:
        permissions = workflow["jobs"]["github-release"].get("permissions", {})
        assert permissions.get("contents") == "write"
