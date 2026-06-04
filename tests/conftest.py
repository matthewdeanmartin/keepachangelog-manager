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
from pathlib import Path

import pytest
from hypothesis import HealthCheck, settings

# Disable deadline globally for Hypothesis tests to prevent flakiness on slow CI/machines.
settings.register_profile(
    "default", deadline=None, suppress_health_check=[HealthCheck.too_slow]
)
settings.load_profile("default")


@pytest.fixture(autouse=True)
def isolate_cwd(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Run each test from a clean temp directory with no ambient config."""

    original = Path.cwd()
    workdir = tmp_path_factory.mktemp("cwd")
    os.chdir(workdir)
    try:
        yield
    finally:
        os.chdir(original)
