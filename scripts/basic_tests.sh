#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="build/basic-tests"

run() {
    printf '==> %s\n' "$*"
    "$@"
}

assert_text_contains() {
    if [[ "$1" != *"$2"* ]]; then
        printf 'expected text to contain %s\n' "$2" >&2
        return 1
    fi
}

assert_empty() {
    if [[ -n "$1" ]]; then
        printf 'expected output to be empty but got: %s\n' "$1" >&2
        return 1
    fi
}

assert_missing() {
    if [[ -e "$1" ]]; then
        printf 'expected %s to be missing\n' "$1" >&2
        return 1
    fi
}

assert_same() {
    if ! cmp -s "$1" "$2"; then
        printf 'expected %s and %s to match\n' "$1" "$2" >&2
        return 1
    fi
}

cd "${ROOT_DIR}"
rm -rf "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT
mkdir -p "${TMP_DIR}/service" "${TMP_DIR}/exports"

cat > "${TMP_DIR}/CHANGELOG.md" <<'EOF'
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- New feature

### Changed
- Changed another feature

## [1.0.0] - 2022-03-14
### Removed
- Removed deprecated API call

### Fixed
- Fixed some bug

## [0.9.4] - 2022-03-13
### Deprecated
- Deprecated public API call
EOF

cp "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/service/CHANGELOG.md"
cp "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

cat > "${TMP_DIR}/unordered.md" <<'EOF'
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Feature A

## [1.0.0] - 2024-01-01
### Added
- Initial release

## [2.0.0] - 2024-06-01
### Added
- Big change
EOF

cp "${TMP_DIR}/unordered.md" "${TMP_DIR}/unordered.original.md"

cat > "${TMP_DIR}/config.toml" <<EOF
[[components]]
name = "Service Component"
changelog = "${TMP_DIR}/service/CHANGELOG.md"
EOF

run uv sync --frozen >/dev/null

run uv run changelogmanager --help >/dev/null
run uv run python -m changelogmanager --help >/dev/null
run uv run changelogmanager validate --help >/dev/null
run uv run changelogmanager create --help >/dev/null
run uv run changelogmanager config --help >/dev/null
run uv run changelogmanager config init --help >/dev/null
run uv run changelogmanager skill --help >/dev/null
run uv run changelogmanager skill export --help >/dev/null
run uv run changelogmanager add --help >/dev/null
run uv run changelogmanager remove --help >/dev/null
run uv run changelogmanager edit --help >/dev/null
run uv run changelogmanager version --help >/dev/null
run uv run changelogmanager release --help >/dev/null
run uv run changelogmanager to-json --help >/dev/null
run uv run changelogmanager to-html --help >/dev/null
run uv run changelogmanager github-release --help >/dev/null
run uv run changelogmanager github-pr --help >/dev/null
run uv run changelogmanager gitlab-release --help >/dev/null
run uv run changelogmanager backfill --help >/dev/null
run uv run changelogmanager from-commits --help >/dev/null
run uv run changelogmanager gui --help >/dev/null

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" validate --dry-run >/dev/null
validate_fix_output="$(uv run changelogmanager --input-file "${TMP_DIR}/unordered.md" validate --fix --no-format --dry-run)"
assert_text_contains "${validate_fix_output}" "Dry run:"
assert_same "${TMP_DIR}/unordered.md" "${TMP_DIR}/unordered.original.md"
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --reference previous --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --reference future --dry-run >/dev/null
run uv run changelogmanager --config "${TMP_DIR}/config.toml" --component "Service Component" version --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/generated/CHANGELOG.md" create --dry-run >/dev/null
assert_missing "${TMP_DIR}/generated/CHANGELOG.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" add --change-type added --message "Smoke test entry" --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

remove_list_output="$(uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" remove --list)"
assert_text_contains "${remove_list_output}" "[added] 0: New feature"
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" remove --change-type added --index 0 --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" edit --change-type added --index 0 --message "Edited smoke test entry" --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" release --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" release --override-version v1.1.0 --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" to-json --file-name "${TMP_DIR}/CHANGELOG.json" --dry-run >/dev/null
assert_missing "${TMP_DIR}/CHANGELOG.json"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" to-html --file-name "${TMP_DIR}/CHANGELOG.html" --dry-run >/dev/null
assert_missing "${TMP_DIR}/CHANGELOG.html"

config_json="$(uv run changelogmanager --config "${TMP_DIR}/config.toml" --json config)"
assert_text_contains "${config_json}" '"config_source": "explicit --config'
assert_text_contains "${config_json}" '"config"'

future_json="$(uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" --json version --reference future)"
assert_text_contains "${future_json}" '"version": "1.1.0"'

quiet_output="$(uv run changelogmanager --quiet --input-file "${TMP_DIR}/CHANGELOG.md" version --reference current)"
assert_empty "${quiet_output}"

run uv run changelogmanager skill export --path "${TMP_DIR}/exports" --dry-run >/dev/null
assert_missing "${TMP_DIR}/exports/keepachangelog-manager-cli"

run uv run changelogmanager --error-format github --input-file "${TMP_DIR}/CHANGELOG.md" github-release --repository example/repo --github-token token --dry-run >/dev/null
run uv run changelogmanager --error-format llvm --input-file "${TMP_DIR}/CHANGELOG.md" github-release --repository example/repo --github-token token --release --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" github-pr --repository example/repo --head docs/changelog --base main --github-token token --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" gitlab-release --project example/group --gitlab-token token --dry-run >/dev/null


# `config init` is interactive-only; its prompt flow, the GUI argv builders, and
# `gui.run_cli` are exercised in the pytest suite (tests/test_basic/test_gui.py,
# test_skill_bundle.py, test_cli.py). Here we smoke-test the non-interactive
# `config` read path against a standalone TOML config file.
config_read_json="$(uv run changelogmanager --config "${TMP_DIR}/config.toml" --json config)"
assert_text_contains "${config_read_json}" '"config_source": "explicit --config'
assert_text_contains "${config_read_json}" "Service Component"
echo "Done"
