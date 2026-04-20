#!/usr/bin/env bash
# Start Xvfb for headless GUI tests, then run whatever command was passed.
set -e

Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
XVFB_PID=$!
trap 'kill $XVFB_PID 2>/dev/null' EXIT

# Give Xvfb a moment to start
sleep 0.5

exec "$@"
