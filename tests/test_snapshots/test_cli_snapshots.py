"""Snapshot tests for deterministic CLI output.

These tests intentionally live outside the normal test suite so they don't
run on every ``make test`` invocation (they're slower and write files).
Run them explicitly::

    uv run pytest tests/test_snapshots/           # check snapshots
    uv run pytest tests/test_snapshots/ --snapshot-update  # regenerate

They are also wired into ``make prerelease`` via ``make snapshot-check``.

Why syrupy + mdformat?
  * syrupy stores snapshots as committed text files alongside the tests.
    ``--snapshot-update`` regenerates them; a plain run fails if they drift.
  * mdformat normalises Markdown whitespace so cosmetic re-formatting
    (blank lines, list indentation) does not produce false-alarm failures.
"""

import json
from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.test_snapshots.conftest import normalise_json, normalise_md, normalise_paths


# ---------------------------------------------------------------------------
# create command
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestCreateSnapshot:
    def test_create_produces_canonical_file(
        self, tmp_path: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        cl = tmp_path / "NEW.md"
        rc, _ = run_cli("--input-file", str(cl), "create")
        assert rc == 0
        assert normalise_md(cl.read_text()) == snapshot


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestVersionSnapshot:
    def test_current_version(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(full_changelog), "version", "--reference", "current")
        assert rc == 0
        assert out == snapshot

    def test_previous_version(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(full_changelog), "version", "--reference", "previous")
        assert rc == 0
        assert out == snapshot

    def test_future_version(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(full_changelog), "version", "--reference", "future")
        assert rc == 0
        assert out == snapshot

    def test_minimal_current_version(
        self, minimal_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(minimal_changelog), "version")
        assert rc == 0
        assert out == snapshot


# ---------------------------------------------------------------------------
# validate command
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestValidateSnapshot:
    def test_validate_full_changelog_passes(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(full_changelog), "validate")
        assert rc == 0
        assert out == snapshot

    def test_validate_minimal_changelog_passes(
        self, minimal_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(minimal_changelog), "validate")
        assert rc == 0
        assert out == snapshot


# ---------------------------------------------------------------------------
# to-json command
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestToJsonSnapshot:
    def test_full_changelog_json_output(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        out_path = full_changelog.parent / "CHANGELOG.json"
        rc, _ = run_cli("--input-file", str(full_changelog), "to-json", "--file-name", str(out_path))
        assert rc == 0
        assert normalise_json(out_path.read_text()) == snapshot

    def test_minimal_changelog_json_output(
        self, minimal_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        out_path = minimal_changelog.parent / "CHANGELOG.json"
        rc, _ = run_cli("--input-file", str(minimal_changelog), "to-json", "--file-name", str(out_path))
        assert rc == 0
        assert normalise_json(out_path.read_text()) == snapshot

    def test_no_unreleased_json_output(
        self, no_unreleased_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        out_path = no_unreleased_changelog.parent / "CHANGELOG.json"
        rc, _ = run_cli("--input-file", str(no_unreleased_changelog), "to-json", "--file-name", str(out_path))
        assert rc == 0
        assert normalise_json(out_path.read_text()) == snapshot


# ---------------------------------------------------------------------------
# add command
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestAddSnapshot:
    def test_add_entry_updates_file(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, _ = run_cli(
            "--input-file", str(full_changelog),
            "add", "--change-type", "added", "--message", "Snapshot test entry",
        )
        assert rc == 0
        assert normalise_md(full_changelog.read_text()) == snapshot

    def test_add_fixed_entry(
        self, minimal_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, _ = run_cli(
            "--input-file", str(minimal_changelog),
            "add", "--change-type", "fixed", "--message", "Fixed a regression in parsing",
        )
        assert rc == 0
        assert normalise_md(minimal_changelog.read_text()) == snapshot


# ---------------------------------------------------------------------------
# release command (dry-run only — avoids interactive prompt)
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestReleaseSnapshot:
    def test_release_dry_run_stdout(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli(
            "--input-file", str(full_changelog),
            "release", "--dry-run", "--override-version", "1.3.0",
        )
        assert rc == 0
        assert normalise_paths(out, full_changelog.parent) == snapshot

    def test_release_writes_file(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, _ = run_cli(
            "--input-file", str(full_changelog),
            "release", "--yes", "--override-version", "1.3.0",
        )
        assert rc == 0
        assert normalise_md(full_changelog.read_text()) == snapshot


# ---------------------------------------------------------------------------
# remove --list command
# ---------------------------------------------------------------------------


@pytest.mark.snapshot
class TestRemoveListSnapshot:
    def test_list_unreleased_entries(
        self, full_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(full_changelog), "remove", "--list")
        assert rc == 0
        assert out == snapshot

    def test_list_no_unreleased(
        self, no_unreleased_changelog: Path, run_cli, snapshot: SnapshotAssertion
    ) -> None:
        rc, out = run_cli("--input-file", str(no_unreleased_changelog), "remove", "--list")
        assert rc == 0
        assert out == snapshot
