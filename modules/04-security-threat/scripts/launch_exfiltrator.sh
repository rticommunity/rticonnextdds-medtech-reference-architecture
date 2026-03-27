#!/bin/bash
# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# launch_exfiltrator.sh — Launch the Threat Exfiltrator GUI application.
# Run from the modules/04-security-threat/ directory.

source ./scripts/common.sh

python3 src/ThreatExfiltrator.py
