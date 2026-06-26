"""Tests for the vendored jiggle-version subset.

These exercise the real vendored functions (no mocking) so the dependency-free
reimplementations of ``find_source_files`` and ``update_pyproject_toml`` stay
faithful to what ``bump_version_files`` expects. Every file operation stays
inside ``tmp_path`` per the repo's isolate_cwd rule.
"""

from __future__ import annotations

from changelogmanager import version_bumper
from changelogmanager.vendor import jiggle_version


def test_vendored_public_surface_is_importable_and_callable():
    for name in ("find_source_files", "update_pyproject_toml", "update_python_file"):
        assert hasattr(jiggle_version, name)
        assert callable(getattr(jiggle_version, name))


def test_update_pyproject_toml_rewrites_project_version_preserving_format(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"  # current\n\n'
        "[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )

    jiggle_version.update_pyproject_toml(pyproject, "2.5.0")

    text = pyproject.read_text(encoding="utf-8")
    assert 'version = "2.5.0"  # current' in text
    # Everything else is untouched.
    assert 'name = "demo"' in text
    assert "[tool.ruff]\nline-length = 100" in text


def test_update_pyproject_toml_uses_setuptools_table_when_no_project_version(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.setuptools]\nversion = "0.1.0"\n',
        encoding="utf-8",
    )

    jiggle_version.update_pyproject_toml(pyproject, "3.0.0")

    assert 'version = "3.0.0"' in pyproject.read_text(encoding="utf-8")


def test_update_pyproject_toml_noop_when_no_version_key(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    original = '[project]\nname = "demo"\n'
    pyproject.write_text(original, encoding="utf-8")

    jiggle_version.update_pyproject_toml(pyproject, "9.9.9")

    assert pyproject.read_text(encoding="utf-8") == original


def test_update_python_file_rewrites_dunder_version(tmp_path):
    module = tmp_path / "mod.py"
    module.write_text("__version__ = '0.1.0'\nFOO = 1\n", encoding="utf-8")

    jiggle_version.update_python_file(module, "4.1.2")

    assert "__version__ = '4.1.2'" in module.read_text(encoding="utf-8")


def test_find_source_files_targets_version_files_and_skips_ignored_dirs(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0"\n', "utf-8")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("__version__ = '0'\n", "utf-8")
    (pkg / "_version.py").write_text("__version__ = '0'\n", "utf-8")
    (pkg / "notes.txt").write_text("ignore me\n", "utf-8")
    # An ignored dir must not be descended into.
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "__init__.py").write_text("__version__ = '0'\n", "utf-8")

    found = set(jiggle_version.find_source_files(tmp_path))

    assert tmp_path / "pyproject.toml" in found
    assert pkg / "__init__.py" in found
    assert pkg / "_version.py" in found
    assert pkg / "notes.txt" not in found
    assert venv / "__init__.py" not in found


def test_bump_version_files_end_to_end_uses_vendored_helpers(tmp_path):
    """No mocking: real vendored bump across pyproject + a package __version__."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    pkg = tmp_path / "demo"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("__version__ = '0.1.0'\n", encoding="utf-8")

    changed = version_bumper.bump_version_files("1.4.0", project_root=tmp_path)

    assert (tmp_path / "pyproject.toml") in changed
    assert (pkg / "__init__.py") in changed
    assert 'version = "1.4.0"' in (tmp_path / "pyproject.toml").read_text("utf-8")
    assert "__version__ = '1.4.0'" in (pkg / "__init__.py").read_text("utf-8")
