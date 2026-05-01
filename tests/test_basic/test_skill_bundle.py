from pathlib import Path

from changelogmanager.skill_bundle import SKILL_NAME, export_skill, resolve_export_path


def test_resolve_export_path_accepts_root_or_full_skill_path(tmp_path):
    root = tmp_path / "skills"
    full = root / SKILL_NAME

    assert resolve_export_path(root) == full
    assert resolve_export_path(full) == full


def test_export_skill_copies_bundled_skill(tmp_path):
    exported = export_skill(tmp_path)

    assert exported == tmp_path / SKILL_NAME
    skill_file = exported / "SKILL.md"
    assert skill_file.exists()
    assert "keepachangelog-manager CLI" in skill_file.read_text(encoding="utf-8")
