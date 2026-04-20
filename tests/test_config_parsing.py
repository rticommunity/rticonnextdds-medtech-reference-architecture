#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.
"""Parser and configuration contract tests.

These tests focus on static parsing contracts for launcher configuration files
and parser failure modes in ``module_runner.load_module_config``.
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "resource" / "python"))
module_runner = importlib.import_module("scripts.module_runner")

ARGS_REF_RE = re.compile(r"\$\{args:([^}]+)\}")


def _collect_args_refs(raw: object) -> set[str]:
    """Collect all ${args:<name>} placeholders from nested JSON-like data."""
    refs: set[str] = set()

    if isinstance(raw, str):
        refs.update(ARGS_REF_RE.findall(raw))
    elif isinstance(raw, list):
        for item in raw:
            refs.update(_collect_args_refs(item))
    elif isinstance(raw, dict):
        for value in raw.values():
            refs.update(_collect_args_refs(value))

    return refs


class TestModuleJsonContract:
    """Validate structure and parser-facing invariants of every module.json."""

    def test_module_json_has_required_shapes(self):
        modules = module_runner.discover_modules()
        assert modules, "No modules discovered"

        for module_name, module_dir in modules.items():
            config_path = module_dir / "module.json"
            assert config_path.is_file(), f"Missing module.json for {module_name}: {config_path}"

            with open(config_path, encoding="utf-8") as f:
                raw = json.load(f)

            assert isinstance(raw.get("description"), str) and raw["description"].strip(), (
                f"{module_name}: description must be a non-empty string"
            )

            if "env" in raw:
                assert isinstance(raw["env"], dict), f"{module_name}: env must be an object"
                for key, value in raw["env"].items():
                    assert isinstance(key, str) and key, f"{module_name}: env key must be non-empty string"
                    assert isinstance(value, str), f"{module_name}: env value for {key} must be string"

            args_section = raw.get("args", {})
            assert isinstance(args_section, dict), f"{module_name}: args must be an object"
            for arg_name, spec in args_section.items():
                assert isinstance(arg_name, str) and arg_name, f"{module_name}: args key must be non-empty string"
                assert isinstance(spec, dict), f"{module_name}: args.{arg_name} must be an object"
                assert "true" in spec and "false" in spec, (
                    f"{module_name}: args.{arg_name} must define both 'true' and 'false'"
                )
                assert isinstance(spec["true"], str), f"{module_name}: args.{arg_name}.true must be string"
                assert isinstance(spec["false"], str), f"{module_name}: args.{arg_name}.false must be string"
                if "flag" in spec:
                    assert isinstance(spec["flag"], str) and spec["flag"], (
                        f"{module_name}: args.{arg_name}.flag must be non-empty string"
                    )

            apps = raw.get("apps")
            assert isinstance(apps, dict) and apps, f"{module_name}: apps must be a non-empty object"
            for app_name, command in apps.items():
                assert isinstance(app_name, str) and app_name, f"{module_name}: app name must be non-empty string"
                assert isinstance(command, list) and command, (
                    f"{module_name}: app '{app_name}' command must be a non-empty list"
                )
                assert all(isinstance(tok, str) and tok for tok in command), (
                    f"{module_name}: app '{app_name}' command tokens must be non-empty strings"
                )

    def test_module_json_args_references_are_defined(self):
        modules = module_runner.discover_modules()

        for module_name, module_dir in modules.items():
            with open(module_dir / "module.json", encoding="utf-8") as f:
                raw = json.load(f)

            defined = set(raw.get("args", {}).keys())
            referenced = _collect_args_refs({"env": raw.get("env", {}), "apps": raw.get("apps", {})})
            missing = sorted(referenced - defined)
            assert not missing, f"{module_name}: undefined args placeholders referenced: {', '.join(missing)}"


class TestLoadModuleConfigNegativeParsing:
    """Ensure parser errors are raised for invalid module.json content."""

    @staticmethod
    def _write_config(module_dir: Path, payload: dict) -> None:
        module_dir.mkdir(parents=True, exist_ok=True)
        with open(module_dir / "module.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def test_missing_required_flag_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        module_dir = tmp_path / "bad-module-1"
        self._write_config(
            module_dir,
            {
                "description": "Bad module",
                "args": {"security": {"true": "x", "false": "y"}},
                "setup_library_paths": False,
                "apps": {"A": ["echo", "ok"]},
            },
        )
        monkeypatch.setattr(module_runner.platform_setup, "get_nddshome", lambda: Path("/tmp/nddshome"))

        with pytest.raises(ValueError, match="requires flag"):
            module_runner.load_module_config(module_dir, flags={})

    def test_unknown_placeholder_kind_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        module_dir = tmp_path / "bad-module-2"
        self._write_config(
            module_dir,
            {
                "description": "Bad module",
                "setup_library_paths": False,
                "env": {"X": "${NOPE:value}"},
                "apps": {"A": ["echo", "ok"]},
            },
        )
        monkeypatch.setattr(module_runner.platform_setup, "get_nddshome", lambda: Path("/tmp/nddshome"))

        with pytest.raises(ValueError, match="Unknown placeholder"):
            module_runner.load_module_config(module_dir, flags={})

    def test_undefined_args_reference_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        module_dir = tmp_path / "bad-module-3"
        self._write_config(
            module_dir,
            {
                "description": "Bad module",
                "setup_library_paths": False,
                "apps": {"A": ["${args:not_defined}"]},
            },
        )
        monkeypatch.setattr(module_runner.platform_setup, "get_nddshome", lambda: Path("/tmp/nddshome"))

        with pytest.raises(ValueError, match="Unknown args variable"):
            module_runner.load_module_config(module_dir, flags={})

    def test_args_spec_missing_true_or_false_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        module_dir = tmp_path / "bad-module-4"
        self._write_config(
            module_dir,
            {
                "description": "Bad module",
                "args": {"security": {"false": "x"}},
                "setup_library_paths": False,
                "apps": {"A": ["echo", "ok"]},
            },
        )
        monkeypatch.setattr(module_runner.platform_setup, "get_nddshome", lambda: Path("/tmp/nddshome"))

        with pytest.raises(KeyError):
            module_runner.load_module_config(module_dir, flags={"security": True})
