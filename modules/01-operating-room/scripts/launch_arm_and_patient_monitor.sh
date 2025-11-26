#!/bin/bash
# This script is meant for Module 03 - Remote Remote Teleoperation

# Set up XML-related variables (QoS, XML App Creation, etc.)
source ./scripts/common.sh

# Start the processes
python3 src/Arm.py &
python3 src/PatientMonitor.py &