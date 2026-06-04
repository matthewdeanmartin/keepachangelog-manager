"""Shared pytest fixtures.

Isolate every test from the repository's own configuration. Now that the project
dogfoods changelogmanager (there is a ``[tool.changelogmanager]`` table in the repo's
``pyproject.toml``), tests that invoke the CLI with only ``--input-file`` would
otherwise auto-detect that ambient config when run from the repo directory. Running
each test in a fresh working directory keeps the suite hermetic regardless of where
pytest is launched. Tests that need their own working directory still call
``monkeypatch.chdir(...)`` and simply override this default.
"""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_cwd(tmp_path_factory):
    """Run each test from a clean temp directory with no ambient config."""

    original = os.getcwd()
    workdir = tmp_path_factory.mktemp("cwd")
    os.chdir(workdir)
    try:
        yield
    finally:
        os.chdir(original)
