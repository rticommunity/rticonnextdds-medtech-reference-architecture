#!/bin/bash

# Store the "-s" argument if provided, otherwise default to an empty string
SEC_FLAG=${1:-}

# Apply Security QoS if needed
if [ "$SEC_FLAG" = "-s" ]; then
  echo "Launching applications with Security..."
  APPS_QOS_FILE="../../system_arch/qos/SecureAppsQos.xml"
elif [ -z "$SEC_FLAG" ]; then
  echo "Launching applications without Security..."
  APPS_QOS_FILE="../../system_arch/qos/NonSecureAppsQos.xml"
else
  echo "Unknown argument: $SEC_FLAG. Use -s to run with Security. Don't use any argument to run without security"
  exit 1
fi

QOS_FILE="../../system_arch/qos/Qos.xml"

export NDDS_QOS_PROFILES=$QOS_FILE";"$APPS_QOS_FILE