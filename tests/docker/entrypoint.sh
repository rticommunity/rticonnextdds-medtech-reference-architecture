#!/usr/bin/env bash
#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

# Docker test entrypoint: Start Xvfb for headless GUI tests, then run tests.
# The RTI Connext environment and Python venv are already configured in the Dockerfile.
set -e

# Start Xvfb virtual display for headless GUI testing
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp 2>/dev/null &
XVFB_PID=$!
trap 'kill $XVFB_PID 2>/dev/null || true' EXIT

# Give Xvfb a moment to start
sleep 0.5

# Source RTI & Python environments
eval $(rtienv)
source $VIRTUAL_ENV/bin/activate

# Run pytest from repo root with any passed arguments
# Default to running all tests if no args provided
cd /workspace
exec pytest "${@:-.}"
