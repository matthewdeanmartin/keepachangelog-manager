#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="build/basic-tests"

run() {
    printf '==> %s\n' "$*"
    "$@"
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
mkdir -p "${TMP_DIR}/service"

cat > "${TMP_DIR}/CHANGELOG.md" <<'EOF'
# Changelog

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

cat > "${TMP_DIR}/config.yml" <<EOF
project:
  components:
    - name: Service Component
      changelog: ${TMP_DIR}/service/CHANGELOG.md
EOF

run uv sync --frozen >/dev/null

run uv run changelogmanager --help >/dev/null
run uv run changelogmanager validate --help >/dev/null
run uv run changelogmanager create --help >/dev/null
run uv run changelogmanager add --help >/dev/null
run uv run changelogmanager version --help >/dev/null
run uv run changelogmanager release --help >/dev/null
run uv run changelogmanager to-json --help >/dev/null
run uv run changelogmanager github-release --help >/dev/null

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" validate --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --reference previous --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" version --reference future --dry-run >/dev/null
run uv run changelogmanager --config "${TMP_DIR}/config.yml" --component "Service Component" version --dry-run >/dev/null
run uv run changelogmanager --input-file "${TMP_DIR}/generated/CHANGELOG.md" create --dry-run >/dev/null
assert_missing "${TMP_DIR}/generated/CHANGELOG.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" add --change-type added --message "Smoke test entry" --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" release --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" release --override-version v1.1.0 --dry-run >/dev/null
assert_same "${TMP_DIR}/CHANGELOG.md" "${TMP_DIR}/CHANGELOG.original.md"

run uv run changelogmanager --input-file "${TMP_DIR}/CHANGELOG.md" to-json --file-name "${TMP_DIR}/CHANGELOG.json" --dry-run >/dev/null
assert_missing "${TMP_DIR}/CHANGELOG.json"

run uv run changelogmanager --error-format github --input-file "${TMP_DIR}/CHANGELOG.md" github-release --repository example/repo --github-token token --dry-run >/dev/null
run uv run changelogmanager --error-format llvm --input-file "${TMP_DIR}/CHANGELOG.md" github-release --repository example/repo --github-token token --release --dry-run >/dev/null
echo "Done"