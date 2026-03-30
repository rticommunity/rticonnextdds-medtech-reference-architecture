#!/bin/bash
# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# launch_injector.sh — Launch the Threat Injector GUI application.
# Run from the modules/04-security-threat/ directory.

source ./scripts/common.sh

python3 src/ThreatInjector.py
