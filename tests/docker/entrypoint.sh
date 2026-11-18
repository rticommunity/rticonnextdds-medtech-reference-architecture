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

# Docker test entrypoint: Run browser-mode tests without a display server.
# The RTI Connext environment and Python venv are already configured in the Dockerfile.
set -e

# Source RTI & Python environments
sdk_scripts=("$NDDSHOME"/resource/scripts/rtisetenv_*.bash)
if [[ ${#sdk_scripts[@]} != 1 || ! -f ${sdk_scripts[0]} ]]; then
    echo "Expected one Connext environment script" >&2
    exit 1
fi
source "${sdk_scripts[0]}"
source "$VIRTUAL_ENV/bin/activate"

# Run pytest from repo root with any passed arguments
# Default to running all tests if no args provided
cd /workspace
python resource/python/scripts/smoke_connext_runtime.py
exec python -m pytest "${@:-.}"
