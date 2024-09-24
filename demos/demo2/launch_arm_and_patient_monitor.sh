#!/bin/bash
# Remember to source the .bash file to dynamically load the security libraries

# Store the "-s" argument if provided, otherwise default to an empty string
ARG=${1:-}

if [ "$ARG" = "-s" ]; then
  echo "Launching applications with Security..."
  APPS_QOS_FILE="../../system_arch/qos/SecureAppsQos.xml"
elif [ -z "$ARG" ]; then
  echo "Launching applications without Security..."
  APPS_QOS_FILE="../../system_arch/qos/NonSecureAppsQos.xml"
else
  echo "Unknown argument: $ARG. Use -s to run with Security. Don't use any argument to run without security"
  exit 1
fi

QOS_FILE="../../system_arch/qos/Qos.xml"
DOMAIN_LIBRARY_FILE="../../system_arch/xml_app_creation/DomainLibrary.xml"
PARTICIPANT_LIBRARY_FILE="../../system_arch/xml_app_creation/ParticipantLibrary.xml"

export NDDS_QOS_PROFILES=$QOS_FILE";"$APPS_QOS_FILE";"$DOMAIN_LIBRARY_FILE";"$PARTICIPANT_LIBRARY_FILE

# Start the processes
cd ../demo1
python3 src/Arm.py &
python3 src/PatientMonitor.py &