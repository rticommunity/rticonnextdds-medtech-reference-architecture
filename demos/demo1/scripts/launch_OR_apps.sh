#!/bin/bash
# This script is meant for Demo - Teleoperation

# Set up XML-related variables (QoS, XML App Creation, etc.)
source ./scripts/common.sh

# Start the processes
build/Orchestrator &
build/PatientSensor &
python3 src/Arm.py &
python3 src/PatientMonitor.py &