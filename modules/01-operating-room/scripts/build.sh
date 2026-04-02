#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUILD_DIR="${MODULE_DIR}/build"

mkdir -p "${BUILD_DIR}"
cmake -B "${BUILD_DIR}" -S "${MODULE_DIR}"
cmake --build "${BUILD_DIR}"
