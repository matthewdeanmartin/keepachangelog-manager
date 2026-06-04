#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES_DIR="${ROOT_DIR}/scripts/fixtures"
TMP_DIR="build/basic-integration-tests"

run() {
    printf '==> %s\n' "$*"
    "$@"
}

run_in_dir() {
    local dir="$1"
    shift
    printf '==> (cd %s && %s)\n' "$dir" "$*"
    (
        cd "$dir"
        "$@"
    )
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

assert_before() {
    local first_line
    local second_line
    first_line="$(grep -nF -- "$2" "$1" | head -n1 | cut -d: -f1)"
    second_line="$(grep -nF -- "$3" "$1" | head -n1 | cut -d: -f1)"
    if [[ -z "${first_line}" || -z "${second_line}" || "${first_line}" -ge "${second_line}" ]]; then
        printf 'expected %s to appear before %s in %s\n' "$2" "$3" "$1" >&2
        return 1
    fi
}

cd "${ROOT_DIR}"
rm -rf "${TMP_DIR}"
trap 'rm -rf "${TMP_DIR}"' EXIT
mkdir -p "${TMP_DIR}/"{create,add,release,json,component,html,remove,edit,validate,skill,gitrepo}

cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/add/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/release/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/json/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/html/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/remove/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/edit/CHANGELOG.md"
cp "${FIXTURES_DIR}/sample-changelog.md" "${TMP_DIR}/component/CHANGELOG.md"
sed "s#__CHANGELOG_PATH__#${TMP_DIR}/component/CHANGELOG.md#" \
    "${FIXTURES_DIR}/component-config.template.toml" > "${TMP_DIR}/component/config.toml"

cat > "${TMP_DIR}/validate/CHANGELOG.md" <<'EOF'
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- Feature A

## [1.0.0] - 2024-01-01
### Added
- Initial

## [2.0.0] - 2024-06-01
### Added
- Big change
EOF

cat > "${TMP_DIR}/gitrepo/CHANGELOG.md" <<'EOF'
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-01-01
### Added
- Initial release
EOF

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
component_version="$(uv run changelogmanager --config "${TMP_DIR}/component/config.toml" --component "Service Component" version)"

assert_equals "${current_version}" "1.0.0"
assert_equals "${previous_version}" "0.9.4"
assert_equals "${future_version}" "1.1.0"
assert_equals "${component_version}" "1.0.0"

run uv run changelogmanager --input-file "${TMP_DIR}/json/CHANGELOG.md" to-json --file-name "${TMP_DIR}/json/CHANGELOG.json"
assert_exists "${TMP_DIR}/json/CHANGELOG.json"
assert_contains "${TMP_DIR}/json/CHANGELOG.json" '"version": "unreleased"'

run uv run changelogmanager --input-file "${TMP_DIR}/html/CHANGELOG.md" to-html --file-name "${TMP_DIR}/html/CHANGELOG.html"
assert_exists "${TMP_DIR}/html/CHANGELOG.html"
assert_contains "${TMP_DIR}/html/CHANGELOG.html" "<!DOCTYPE html>"
assert_contains "${TMP_DIR}/html/CHANGELOG.html" "<h1>Changelog</h1>"

uv run changelogmanager --input-file "${TMP_DIR}/remove/CHANGELOG.md" remove --list > "${TMP_DIR}/remove/list.txt"
assert_contains "${TMP_DIR}/remove/list.txt" "[added] 0: New feature"
assert_contains "${TMP_DIR}/remove/list.txt" "[changed] 0: Changed another feature"

run uv run changelogmanager --input-file "${TMP_DIR}/remove/CHANGELOG.md" remove --change-type added --index 0
assert_not_contains "${TMP_DIR}/remove/CHANGELOG.md" "- New feature"

run uv run changelogmanager --input-file "${TMP_DIR}/edit/CHANGELOG.md" edit --change-type changed --index 0 --message "Edited integration entry" --new-change-type fixed
assert_contains "${TMP_DIR}/edit/CHANGELOG.md" "- Edited integration entry"
assert_not_contains "${TMP_DIR}/edit/CHANGELOG.md" "- Changed another feature"

run uv run changelogmanager --input-file "${TMP_DIR}/validate/CHANGELOG.md" validate --fix --no-format
assert_before "${TMP_DIR}/validate/CHANGELOG.md" "## [2.0.0] - 2024-06-01" "## [1.0.0] - 2024-01-01"

run uv run changelogmanager --input-file "${TMP_DIR}/release/CHANGELOG.md" release --override-version v1.1.0 --yes
assert_contains "${TMP_DIR}/release/CHANGELOG.md" "## [1.1.0] - "
assert_not_contains "${TMP_DIR}/release/CHANGELOG.md" "## [Unreleased]"

run uv run changelogmanager skill export --path "${TMP_DIR}/skill"
assert_exists "${TMP_DIR}/skill/keepachangelog-manager-cli/SKILL.md"

run_in_dir "${TMP_DIR}/gitrepo" git init -q
run_in_dir "${TMP_DIR}/gitrepo" git config user.email smoke@example.com
run_in_dir "${TMP_DIR}/gitrepo" git config user.name "Smoke Test"
run_in_dir "${TMP_DIR}/gitrepo" git add CHANGELOG.md
run_in_dir "${TMP_DIR}/gitrepo" git commit -q -m "chore: initial changelog"
run_in_dir "${TMP_DIR}/gitrepo" git tag v1.0.0
printf 'feature one\n' > "${TMP_DIR}/gitrepo/code.txt"
run_in_dir "${TMP_DIR}/gitrepo" git add code.txt
run_in_dir "${TMP_DIR}/gitrepo" git commit -q -m "feat: tagged feature"
run_in_dir "${TMP_DIR}/gitrepo" git tag v1.1.0
printf 'feature two\n' >> "${TMP_DIR}/gitrepo/code.txt"
run_in_dir "${TMP_DIR}/gitrepo" git add code.txt
run_in_dir "${TMP_DIR}/gitrepo" git commit -q -m "fix: tagged fix"
run_in_dir "${TMP_DIR}/gitrepo" git tag v1.2.0
printf 'feature three\n' >> "${TMP_DIR}/gitrepo/code.txt"
run_in_dir "${TMP_DIR}/gitrepo" git add code.txt
run_in_dir "${TMP_DIR}/gitrepo" git commit -q -m "feat: add cli smoke coverage"

run_in_dir "${TMP_DIR}/gitrepo" uv run changelogmanager --input-file CHANGELOG.md backfill --source tags
assert_contains "${TMP_DIR}/gitrepo/CHANGELOG.md" "## [1.2.0] - "
assert_contains "${TMP_DIR}/gitrepo/CHANGELOG.md" "Release notes unavailable; backfilled from tag \`v1.2.0\`."

run_in_dir "${TMP_DIR}/gitrepo" uv run changelogmanager --input-file CHANGELOG.md from-commits
assert_contains "${TMP_DIR}/gitrepo/CHANGELOG.md" "## [Unreleased]"
assert_contains "${TMP_DIR}/gitrepo/CHANGELOG.md" "- add cli smoke coverage"

echo "Done"
