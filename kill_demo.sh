#!/usr/bin/env bash
# Kills any running Digital Operating Room demo processes (native or --web mode).
pkill -f "launch.py 01-operating-room" 2>/dev/null
pkill -f "build/arm64Darwin23clang16.0/modules/01-operating-room" 2>/dev/null
pkill -f "src/Arm.py" 2>/dev/null
pkill -f "src/PatientMonitor.py" 2>/dev/null
pkill -f "src/PatientSensor" 2>/dev/null
echo "Demo processes stopped."
