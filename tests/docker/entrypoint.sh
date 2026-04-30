#!/usr/bin/env bash
# Docker test entrypoint: Start Xvfb for headless GUI tests, then run tests.
# The RTI Connext environment and Python venv are already configured in the Dockerfile.
set -e

# Start Xvfb virtual display for headless GUI testing
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!
trap 'kill $XVFB_PID 2>/dev/null || true' EXIT

# Give Xvfb a moment to start
sleep 0.5

# Source RTI environment (persists across to test command)
source "${NDDSHOME}/resource/scripts/rtisetenv_${CONNEXTDDS_ARCH}.bash"

# Run pytest from repo root with any passed arguments
# Default to running all tests if no args provided
cd /workspace
exec python -m pytest "${@:-.}"
