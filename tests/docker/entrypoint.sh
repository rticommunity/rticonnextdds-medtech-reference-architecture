#!/usr/bin/env bash
# Docker test entrypoint: Run browser-based application tests without a display.
# The RTI Connext environment and Python venv are already configured in the Dockerfile.
set -e

# Source RTI & Python environments
eval $(rtienv)
source $VIRTUAL_ENV/bin/activate

# Run pytest from repo root with any passed arguments
# Default to running all tests if no args provided
cd /workspace
exec pytest "${@:-.}"
