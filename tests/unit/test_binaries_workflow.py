"""Static validation for the PyInstaller binaries pipeline — Phase 4 Slice 5.

The actual binary build only runs on tagged CI, so these tests catch
structural drift (missing OS in the matrix, smoke-test stripped out,
release-attach gating broken) before a real release reaches the
ship-binaries step.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "binaries.yml"
SPEC_PATH = REPO_ROOT / "pyinstaller.spec"


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    parsed = yaml.safe_load(raw)
    assert isinstance(parsed, dict), "binaries.yml did not parse to a mapping"
    return parsed


def _trigger_section(workflow: dict[str, Any]) -> dict[str, Any]:
    """PyYAML maps the bare key ``on:`` to ``True`` — handle both keys."""
    return workflow.get("on") or workflow.get(True)  # type: ignore[return-value]


class TestSpecFile:
    def test_spec_exists(self) -> None:
        assert SPEC_PATH.is_file(), f"missing {SPEC_PATH}"

    def test_spec_entrypoint_is_quoriv_main(self) -> None:
        # PyInstaller treats whatever path is passed first as the script
        # to bootstrap. The package's __main__.py is the canonical entry
        # because it mirrors `python -m quoriv` behaviour for tests.
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert "src/quoriv/__main__.py" in text or "src\\quoriv\\__main__.py" in text

    def test_spec_collects_quoriv_submodules(self) -> None:
        # quoriv.models.* providers are loaded via importlib at runtime —
        # PyInstaller's static analyser won't find them without
        # collect_submodules("quoriv").
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert 'collect_submodules("quoriv")' in text

    def test_spec_lists_provider_hidden_imports(self) -> None:
        # Each registered provider module in quoriv.models.factory must
        # appear in the spec's hiddenimports so the binary works for
        # every provider, not just the default OpenAI path.
        text = SPEC_PATH.read_text(encoding="utf-8")
        for provider in ("openai", "anthropic", "gemini", "ollama", "vllm", "openrouter"):
            assert f"quoriv.models.{provider}" in text, (
                f"spec hiddenimports missing quoriv.models.{provider}"
            )

    def test_spec_outputs_console_binary(self) -> None:
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert "console=True" in text
        assert 'name="quoriv"' in text

    def test_spec_disables_upx(self) -> None:
        # UPX-packed Windows binaries get flagged by Defender SmartScreen —
        # leaving UPX off keeps the false-positive rate low.
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert "upx=False" in text


class TestWorkflowTriggers:
    def test_runs_on_version_tag_push(self, workflow: dict[str, Any]) -> None:
        triggers = _trigger_section(workflow)
        push = triggers.get("push", {})
        assert "v*.*.*" in push.get("tags", [])

    def test_supports_manual_dispatch(self, workflow: dict[str, Any]) -> None:
        triggers = _trigger_section(workflow)
        assert "workflow_dispatch" in triggers


class TestBuildMatrix:
    @pytest.fixture
    def matrix_entries(self, workflow: dict[str, Any]) -> list[dict[str, Any]]:
        return workflow["jobs"]["build"]["strategy"]["matrix"]["include"]

    @pytest.mark.parametrize("os_runner", ["ubuntu-latest", "macos-latest", "windows-latest"])
    def test_matrix_covers_all_three_oses(
        self,
        os_runner: str,
        matrix_entries: list[dict[str, Any]],
    ) -> None:
        # All three OSes must be in the matrix — dropping one silently
        # would ship a release with a missing platform binary.
        runners = {entry["os"] for entry in matrix_entries}
        assert os_runner in runners, f"matrix missing {os_runner}"

    def test_each_matrix_entry_names_artifact_and_binary(
        self,
        matrix_entries: list[dict[str, Any]],
    ) -> None:
        # Each matrix row must declare `artifact` (download name) and
        # `binary` (PyInstaller output filename) so the rename/smoke
        # steps know what to target.
        for entry in matrix_entries:
            assert "artifact" in entry, f"matrix entry {entry!r} missing `artifact`"
            assert "binary" in entry, f"matrix entry {entry!r} missing `binary`"

    def test_windows_entry_uses_exe_suffix(
        self,
        matrix_entries: list[dict[str, Any]],
    ) -> None:
        windows = next(e for e in matrix_entries if e["os"] == "windows-latest")
        assert windows["binary"].endswith(".exe")
        assert windows["artifact"].endswith(".exe")


class TestBuildSteps:
    def test_build_installs_binary_extra(self, workflow: dict[str, Any]) -> None:
        # The `binary` extra carries pyinstaller; the workflow must
        # install it (alongside the runtime extras for provider modules).
        steps = workflow["jobs"]["build"]["steps"]
        commands = " ".join(s.get("run", "") for s in steps if "run" in s)
        assert ".[binary" in commands or '".[binary' in commands

    def test_build_runs_pyinstaller_with_spec(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["build"]["steps"]
        commands = " ".join(s.get("run", "") for s in steps if "run" in s)
        assert "pyinstaller pyinstaller.spec" in commands

    def test_build_smoke_tests_the_binary(self, workflow: dict[str, Any]) -> None:
        # Without this step a silently broken binary (missing import,
        # wrong arch, packed-strip casualty) would happily upload and
        # then 1000 users discover it on launch.
        steps = workflow["jobs"]["build"]["steps"]
        smoke_steps = [s for s in steps if "version" in s.get("run", "")]
        assert smoke_steps, "build job must smoke-test the binary by invoking `version`"

    def test_build_uploads_per_os_artifact(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["build"]["steps"]
        uploads = [s for s in steps if "actions/upload-artifact" in s.get("uses", "")]
        assert uploads, "build job must upload the produced binary"
        # Name is templated per matrix row so each OS gets its own artifact.
        assert "matrix.artifact" in uploads[0]["with"]["name"]


class TestAttachToRelease:
    def test_attach_job_exists(self, workflow: dict[str, Any]) -> None:
        assert "attach-to-release" in workflow["jobs"]

    def test_attach_needs_build(self, workflow: dict[str, Any]) -> None:
        needs = workflow["jobs"]["attach-to-release"].get("needs")
        if isinstance(needs, str):
            assert needs == "build"
        else:
            assert "build" in needs

    def test_attach_gated_to_tag_push(self, workflow: dict[str, Any]) -> None:
        # Manual dispatches must NOT touch the GitHub release.
        condition = workflow["jobs"]["attach-to-release"].get("if", "")
        assert "tags/v" in condition
        assert "push" in condition

    def test_attach_has_contents_write(self, workflow: dict[str, Any]) -> None:
        permissions = workflow["jobs"]["attach-to-release"].get("permissions", {})
        assert permissions.get("contents") == "write"

    def test_attach_uses_softprops_action(self, workflow: dict[str, Any]) -> None:
        steps = workflow["jobs"]["attach-to-release"]["steps"]
        releases = [s for s in steps if "softprops/action-gh-release" in s.get("uses", "")]
        assert releases


class TestPyprojectBinaryExtra:
    def test_pyinstaller_in_binary_extra(self) -> None:
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        binary_extras = data["project"]["optional-dependencies"]["binary"]
        joined = " ".join(binary_extras)
        assert "pyinstaller" in joined.lower()
