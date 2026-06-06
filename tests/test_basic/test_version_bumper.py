import pytest

import changelogmanager.llvm_diagnostics as diagnostics
from changelogmanager import version_bumper


def test_jiggle_available_reflects_import_state(monkeypatch):
    monkeypatch.setattr(version_bumper, "HAS_JIGGLE", True)
    assert version_bumper.jiggle_available() is True

    monkeypatch.setattr(version_bumper, "HAS_JIGGLE", False)
    assert version_bumper.jiggle_available() is False


def test_bump_version_files_requires_optional_dependency(monkeypatch):
    monkeypatch.setattr(version_bumper, "HAS_JIGGLE", False)

    with pytest.raises(diagnostics.Error, match="jiggle-version is required"):
        version_bumper.bump_version_files("1.2.3")


def test_bump_version_files_honors_pyproject_only(monkeypatch, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nversion = '0.1.0'\n", encoding="utf-8")
    updated = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(version_bumper, "HAS_JIGGLE", True)
    monkeypatch.setattr(
        version_bumper,
        "update_pyproject_toml",
        lambda path, version: updated.append(("pyproject", path, version)),
        raising=False,
    )
    monkeypatch.setattr(
        version_bumper,
        "find_source_files",
        lambda _root: pytest.fail("find_source_files should not be called"),
        raising=False,
    )

    changed = version_bumper.bump_version_files("1.2.3", pyproject_only=True)

    assert changed == [pyproject]
    assert updated == [("pyproject", pyproject, "1.2.3")]


def test_bump_version_files_updates_python_sources(monkeypatch, tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[project]\nversion = '0.1.0'\n", encoding="utf-8")
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    init_file = package_dir / "__init__.py"
    init_file.write_text("__version__ = '0.1.0'\n", encoding="utf-8")
    module_file = package_dir / "module.py"
    module_file.write_text("__version__ = '0.1.0'\n", encoding="utf-8")
    notes_file = package_dir / "notes.txt"
    notes_file.write_text("0.1.0\n", encoding="utf-8")
    updated = []

    monkeypatch.setattr(version_bumper, "HAS_JIGGLE", True)
    monkeypatch.setattr(
        version_bumper,
        "update_pyproject_toml",
        lambda path, version: updated.append(("pyproject", path, version)),
        raising=False,
    )
    monkeypatch.setattr(
        version_bumper,
        "update_python_file",
        lambda path, version: updated.append(("python", path, version)),
        raising=False,
    )
    monkeypatch.setattr(
        version_bumper,
        "find_source_files",
        lambda _root: [pyproject, init_file, module_file, notes_file],
        raising=False,
    )

    changed = version_bumper.bump_version_files("2.0.0", project_root=tmp_path)

    assert changed == [pyproject, init_file, module_file]
    assert updated == [
        ("pyproject", pyproject, "2.0.0"),
        ("python", init_file, "2.0.0"),
        ("python", module_file, "2.0.0"),
    ]
