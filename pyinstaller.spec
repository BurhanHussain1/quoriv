# PyInstaller spec for the Quoriv single-file binary.
#
# Targets: Linux / macOS / Windows. Invoke via `pyinstaller pyinstaller.spec`
# (the binaries.yml workflow does this on a matrix runner per OS).
#
# The provider modules under `quoriv.models.*` are loaded via
# `importlib.import_module` at runtime, so PyInstaller's static analyser
# does not see them. We list them explicitly under `hiddenimports`
# alongside the LangChain provider packages each one ``from ...``
# imports. Without these the binary works for the default OpenAI path
# but crashes the moment a user picks a different provider.

# ruff: noqa: F821 — `Analysis`, `PYZ`, `EXE` are injected by PyInstaller at exec time.

from PyInstaller.utils.hooks import collect_submodules

_HIDDEN_IMPORTS: list[str] = [
    # Provider modules (lazy-loaded via importlib from quoriv.models.factory).
    "quoriv.models.openai",
    "quoriv.models.anthropic",
    "quoriv.models.gemini",
    "quoriv.models.ollama",
    "quoriv.models.vllm",
    "quoriv.models.openrouter",
    # LangChain provider packages each provider module imports from.
    "langchain_openai",
    "langchain_anthropic",
    "langchain_google_genai",
    "langchain_ollama",
    # DeepAgents pulls these in dynamically through its middleware stack.
    "langchain.agents.factory",
    "langchain_anthropic.middleware.prompt_caching",
]

# Pick up every quoriv submodule + LangChain runtime pieces that often
# evade the static analyser (chains, tracers, hub).
_HIDDEN_IMPORTS += collect_submodules("quoriv")
_HIDDEN_IMPORTS += collect_submodules("langchain")
_HIDDEN_IMPORTS += collect_submodules("langchain_core")
_HIDDEN_IMPORTS += collect_submodules("langgraph")
_HIDDEN_IMPORTS += collect_submodules("deepagents")


a = Analysis(
    ["src/quoriv/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy dev-only stuff that shouldn't ship in the binary.
        "pytest",
        "mypy",
        "ruff",
        "mkdocs",
        "mkdocs_material",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="quoriv",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX often trips Windows Defender false-positives — keep off.
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
