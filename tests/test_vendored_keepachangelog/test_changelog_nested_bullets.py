"""Nested sub-list bullets must be preserved, not flattened or rejected.

Nested bullets are valid Markdown and common in real changelogs (e.g.
bash2yaml's "Traceless mode" entry). The parser folds each indented bullet into
its parent entry string as an embedded ``\\n  - child`` line, so the flat
``list[str]`` model is unchanged and ``from_dict`` round-trips the nesting.
"""

import io

from changelogmanager.vendor import keepachangelog

NESTED_CHANGELOG = """# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-07-04
### Added
- **Traceless mode** with zero footprint in the working tree:
  - New `traceless` command group: `adopt`, `compile`, and `shred`.
  - Composable `compile` flags: `--no-header`, `--no-fences`.
- Single line entry.
"""


def parse(text: str):
    with io.StringIO(text) as reader:
        return keepachangelog.to_dict(reader)


def test_nested_bullets_fold_into_parent_entry():
    result = parse(NESTED_CHANGELOG)

    added = result["1.0.0"]["added"]
    assert len(added) == 2
    assert added[0] == (
        "**Traceless mode** with zero footprint in the working tree:"
        "\n  - New `traceless` command group: `adopt`, `compile`, and `shred`."
        "\n  - Composable `compile` flags: `--no-header`, `--no-fences`."
    )
    assert added[1] == "Single line entry."


def test_nested_bullets_round_trip():
    rendered = keepachangelog.from_dict(parse(NESTED_CHANGELOG))

    assert "\n- **Traceless mode**" in rendered
    assert "\n  - New `traceless` command group" in rendered
    # Round-trip is stable: re-parsing the render yields the same model.
    assert (
        parse(rendered)["1.0.0"]["added"] == parse(NESTED_CHANGELOG)["1.0.0"]["added"]
    )


def test_wrapped_continuation_of_nested_bullet():
    text = NESTED_CHANGELOG.replace(
        "  - Composable `compile` flags: `--no-header`, `--no-fences`.\n",
        "  - Composable `compile` flags: `--no-header`,\n    `--no-fences`.\n",
    )
    added = parse(text)["1.0.0"]["added"]
    assert added[0].endswith(
        "\n  - Composable `compile` flags: `--no-header`, `--no-fences`."
    )


def test_deeper_nesting_keeps_two_spaces_per_level():
    text = NESTED_CHANGELOG.replace(
        "- Single line entry.\n",
        "- Parent.\n  - Child.\n    - Grandchild.\n",
    )
    added = parse(text)["1.0.0"]["added"]
    assert added[-1] == "Parent.\n  - Child.\n    - Grandchild."
