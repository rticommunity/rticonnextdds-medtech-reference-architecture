#!/bin/bash
# Store the "-s" argument if provided, otherwise default to an empty string
SEC_FLAG=${1:-}

# Apply Security QoS if needed
if [ "$SEC_FLAG" = "-s" ]; then
  echo "This example does not support running with Security. Please run without the -s flag."
  exit 1
else
  echo "Running without Security..."
fi

# Set up XML-related variables (QoS, XML App Creation, etc.)
source ./scripts/variables.sh

# Start the process
$NDDSHOME/bin/rtiwebintegrationservice -listeningPorts $PUBLIC_PORT -cfgFile ./xml_config/wis_service.xml -cfgName MotorControlWebApp -documentRoot $DOC_ROOT -enableKeepAlive yes -enableWebSockets
