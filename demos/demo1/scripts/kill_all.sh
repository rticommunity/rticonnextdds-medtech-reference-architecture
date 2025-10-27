echo "Killing all applications..."

pkill ArmController
pkill Orchestrator
pkill PatientSensor
pkill -f PatientMonitor.py
pkill -f Arm.py

# Kill Services from other demos if running
pkill -f rtirecordingservice
pkill -f rticlouddiscoveryservice
pkill -f rtiroutingservice