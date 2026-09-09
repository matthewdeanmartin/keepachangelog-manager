"""Guards for the bundled skill's YAML frontmatter.

Reported bug: running bare ``mdformat`` (without ``mdformat-frontmatter``) on
``SKILL.md`` rewrote the ``---`` fences into a thematic break and folded the
keys into an ATX heading. The skill still installed and appeared in the skill
list, but its description rendered as a row of underscores, so no agent ever
selected it -- a silent failure with no error at export or load time.
"""

from __future__ import annotations

import pytest

from changelogmanager import skill_bundle
from changelogmanager.skill_bundle import (
    SkillFrontmatterError,
    parse_skill_frontmatter,
    validate_skill_dir,
)

# Exactly what bare mdformat turned the header into.
MANGLED_HEADER = (
    "______________________________________________________________________\n"
    "\n"
    "## name: keepachangelog-manager-cli description: Use changelogmanager CLI "
    "commands correctly for changelog, config, export, release, and skill workflows.\n"
    "\n"
    "# keepachangelog-manager CLI\n"
)

GOOD_HEADER = "---\nname: demo-skill\ndescription: A description agents can select on.\n---\n\n# Demo\n"


def test_bundled_skill_has_valid_frontmatter():
    """The shipped skill must parse -- this is the regression guard."""
    text = skill_bundle.bundled_skill_root().joinpath("SKILL.md").read_bytes()
    fields = parse_skill_frontmatter(text.decode("utf-8"))

    assert fields["name"] == skill_bundle.SKILL_NAME
    assert fields["description"]
    # The mdformat damage signature must not be back.
    assert not fields["description"].startswith("___")


def test_parse_accepts_a_well_formed_header():
    fields = parse_skill_frontmatter(GOOD_HEADER)
    assert fields == {
        "name": "demo-skill",
        "description": "A description agents can select on.",
    }


def test_parse_rejects_the_mdformat_mangled_header():
    with pytest.raises(SkillFrontmatterError, match="must start with a '---'"):
        parse_skill_frontmatter(MANGLED_HEADER)


def test_parse_rejects_an_unterminated_block():
    with pytest.raises(SkillFrontmatterError, match="not terminated"):
        parse_skill_frontmatter("---\nname: x\ndescription: y\n\n# Body\n")


@pytest.mark.parametrize(
    "body",
    [
        "---\ndescription: no name here.\n---\n",
        "---\nname: x\n---\n",
        "---\nname:\ndescription: empty name.\n---\n",
    ],
)
def test_parse_requires_non_empty_name_and_description(body):
    with pytest.raises(SkillFrontmatterError, match="missing a non-empty"):
        parse_skill_frontmatter(body)


def test_validate_skill_dir_reports_a_missing_file(tmp_path):
    with pytest.raises(SkillFrontmatterError, match="Cannot read"):
        validate_skill_dir(tmp_path)


def test_export_skill_produces_a_valid_skill(tmp_path):
    target = skill_bundle.export_skill(tmp_path)

    fields = validate_skill_dir(target)
    assert fields["name"] == skill_bundle.SKILL_NAME
    assert (target / "SKILL.md").read_text(encoding="utf-8").startswith("---\n")
