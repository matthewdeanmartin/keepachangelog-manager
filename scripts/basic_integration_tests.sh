#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES_DIR="${ROOT_DIR}/scripts/fixtures"
TMP_DIR="build/basic-integration-tests"

run() {
    printf '==> %s\n' "$*"
    "$@"
}

assert_exists() {
    if [[ ! -e "$1" ]]; then
        printf 'expected %s to exist\n' "$1" >&2
        return 1
    fi
}

assert_not_contains() {
    if grep -Fq -- "$2" "$1"; then
        printf 'expected %s to not contain %s\n' "$1" "$2" >&2
        return 1
    fi
}

assert_contains() {
    if ! grep -Fq -- "$2" "$1"; then
        printf 'expected %s to contain %s\n' "$1" "$2" >&2
        return 1
    fi
}

assert_equals() {
    if [[ "$1" != "$2" ]]; then
        printf 'expected [%s] but got [%s]\n' "$2" "$1" >&2
        return 1
    fi
}

cd "${ROOT_DIR}"
rm -rf "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT
mkdir -p "${TMP_DIR}/"{create,add,release,json,component}

cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/add/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/release/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/json/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/component/CHANGELOG.md"
sed "s#__CHANGELOG_PATH__#${TMP_DIR}/component/CHANGELOG.md#" \
    "${FIXTURES_DIR}/component-config.template.yml" > "${TMP_DIR}/component/config.yml"

run uv sync --frozen >/dev/null

run uv run changelogmanager --input-file "${TMP_DIR}/create/CHANGELOG.md" create
assert_exists "${TMP_DIR}/create/CHANGELOG.md"
assert_contains "${TMP_DIR}/create/CHANGELOG.md" "# Changelog"
assert_contains "${TMP_DIR}/create/CHANGELOG.md" "Keep a Changelog"

run uv run changelogmanager --input-file "${TMP_DIR}/add/CHANGELOG.md" add --change-type added --message "Integration entry"
assert_contains "${TMP_DIR}/add/CHANGELOG.md" "- Integration entry"

current_version="$(uv run changelogmanager --input-file "${TMP_DIR}/add/CHANGELOG.md" version)"
previous_version="$(uv run changelogmanager --input-file "${TMP_DIR}/add/CHANGELOG.md" version --reference previous)"
future_version="$(uv run changelogmanager --input-file "${TMP_DIR}/add/CHANGELOG.md" version --reference future)"
component_version="$(uv run changelogmanager --config "${TMP_DIR}/component/config.yml" --component "Service Component" version)"

assert_equals "${current_version}" "1.0.0"
assert_equals "${previous_version}" "0.9.4"
assert_equals "${future_version}" "1.1.0"
assert_equals "${component_version}" "1.0.0"

run uv run changelogmanager --input-file "${TMP_DIR}/json/CHANGELOG.md" to-json --file-name "${TMP_DIR}/json/CHANGELOG.json"
assert_exists "${TMP_DIR}/json/CHANGELOG.json"
assert_contains "${TMP_DIR}/json/CHANGELOG.json" '"version": "unreleased"'

run uv run changelogmanager --input-file "${TMP_DIR}/release/CHANGELOG.md" release --override-version v1.1.0
assert_contains "${TMP_DIR}/release/CHANGELOG.md" "## [1.1.0] - "
assert_not_contains "${TMP_DIR}/release/CHANGELOG.md" "## [Unreleased]"

echo "Done"
