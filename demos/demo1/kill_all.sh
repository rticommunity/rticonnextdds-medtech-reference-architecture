echo "Killing all applications..."

pkill ArmController
pkill Orchestrator
pkill PatientSensor
pkill -f PatientMonitor.py
pkill -f Arm.py