#!/bin/bash
# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# kill_all.sh — Terminate all Module 04 threat application processes.
# Run from the modules/04-security-threat/ directory.

pkill -f "ThreatInjector.py" 2>/dev/null && echo "Stopped ThreatInjector" || true
pkill -f "ThreatExfiltrator.py" 2>/dev/null && echo "Stopped ThreatExfiltrator" || true

# Also kill headless threat participants used by tests
pkill -f "threat_headless.py" 2>/dev/null || true

echo "All module 04 processes stopped."
