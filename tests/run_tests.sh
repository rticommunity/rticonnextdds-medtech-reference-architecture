#!/usr/bin/env bash
# Run all module test suites sequentially from the repo root.
# Usage: tests/run_tests.sh [-v] [-- extra-pytest-args]
#
# Discovers test targets automatically:
#   1. The repo-level tests/ directory (this script's own directory)
#   2. Any module under modules/ that contains a tests/ subdirectory
#
# Exits non-zero if any suite fails.
# Wrap with ``xvfb-run -a`` for headless environments (CI).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

failed=0

# --- Repo-level tests (tests/) ---
echo ""
echo "========================================"
echo "  Testing tests/ (repo-level)"
echo "========================================"
if ! (cd "${REPO_ROOT}" && python -m pytest tests/ "$@"); then
    failed=1
fi

# --- Module tests (modules/*/tests/) ---
for mod_tests in "${REPO_ROOT}"/modules/*/tests/; do
    [[ -d "${mod_tests}" ]] || continue
    mod_dir="$(dirname "${mod_tests}")"
    mod_name="${mod_dir#"${REPO_ROOT}/"}"
    echo ""
    echo "========================================"
    echo "  Testing ${mod_name}"
    echo "========================================"
    if ! (cd "${mod_dir}" && python -m pytest tests/ "$@"); then
        failed=1
    fi
done

if [[ $failed -ne 0 ]]; then
    echo ""
    echo "SOME MODULES FAILED"
    exit 1
fi

echo ""
echo "ALL MODULES PASSED"
