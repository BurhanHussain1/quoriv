"""Tests for `quoriv.repo.ast` — extension detection + parser registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from quoriv.repo.ast import (
    LANGUAGE_BY_EXTENSION,
    detect_language,
    get_parser,
    is_available,
)


class TestDetectLanguage:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("foo.py", "python"),
            ("foo.pyi", "python"),
            ("foo.js", "javascript"),
            ("foo.mjs", "javascript"),
            ("foo.ts", "typescript"),
            ("foo.tsx", "tsx"),
            ("foo.go", "go"),
            ("foo.rs", "rust"),
            ("foo.java", "java"),
            ("foo.kt", "kotlin"),
            ("foo.c", "c"),
            ("foo.cpp", "cpp"),
            ("foo.cs", "csharp"),
            ("foo.rb", "ruby"),
            ("foo.php", "php"),
            ("foo.sh", "bash"),
            ("foo.lua", "lua"),
            ("foo.swift", "swift"),
            ("foo.json", "json"),
            ("foo.yaml", "yaml"),
            ("foo.toml", "toml"),
        ],
    )
    def test_known_extensions(self, path: str, expected: str) -> None:
        assert detect_language(path) == expected

    def test_unknown_extension_returns_none(self) -> None:
        assert detect_language("foo.xyz") is None

    def test_no_extension_returns_none(self) -> None:
        assert detect_language("Makefile") is None

    def test_case_insensitive(self) -> None:
        assert detect_language("Foo.PY") == "python"
        assert detect_language("Bar.RS") == "rust"

    def test_accepts_path_object(self, tmp_path: Path) -> None:
        assert detect_language(tmp_path / "a.go") == "go"

    def test_path_does_not_need_to_exist(self) -> None:
        # The function is path-suffix-only; never touches the filesystem.
        assert detect_language("/definitely/does/not/exist.rs") == "rust"


class TestLanguageTable:
    def test_table_is_non_empty(self) -> None:
        assert len(LANGUAGE_BY_EXTENSION) > 20

    def test_every_key_is_dotted_extension(self) -> None:
        for ext in LANGUAGE_BY_EXTENSION:
            assert ext.startswith("."), f"extension {ext!r} missing leading dot"

    def test_every_value_is_a_string(self) -> None:
        for ext, lang in LANGUAGE_BY_EXTENSION.items():
            assert isinstance(lang, str), f"{ext} → {lang!r} not a string"
            assert lang  # non-empty


class TestIsAvailable:
    def test_returns_true_in_test_env(self) -> None:
        # The dev env always installs the ``ast`` extra (per pyproject's
        # CI matrix); if this fails it means the extra is missing in this
        # virtualenv and the rest of the slice tests would also fail.
        assert is_available() is True


class TestGetParser:
    def test_returns_parser_for_python(self) -> None:
        parser = get_parser("python")
        tree = parser.parse("x = 1\n")
        assert tree.root_node().kind() == "module"

    def test_returns_parser_for_go(self) -> None:
        parser = get_parser("go")
        tree = parser.parse("package main\n")
        assert tree.root_node().kind() == "source_file"

    def test_unknown_language_raises_lookuperror(self) -> None:
        with pytest.raises(LookupError):
            get_parser("definitely-not-a-language")
