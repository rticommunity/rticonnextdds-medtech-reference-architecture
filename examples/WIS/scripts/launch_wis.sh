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
export NDDS_QOS_PROFILES="../../system_arch/Types.xml;$NDDS_QOS_PROFILES"

TYPES_FILE="../../system_arch/Types.xml"
QOS_FILE="../../system_arch/qos/Qos.xml"
APPS_QOS_FILE="../../system_arch/qos/NonSecureAppsQos.xml"
DOMAIN_LIBRARY_FILE="../../system_arch/xml_app_creation/DomainLibrary.xml"
PARTICIPANT_LIBRARY_FILE="../../system_arch/xml_app_creation/ParticipantLibrary.xml"

export NDDS_QOS_PROFILES=$TYPES_FILE";"$QOS_FILE";"$APPS_QOS_FILE";"$DOMAIN_LIBRARY_FILE";"$PARTICIPANT_LIBRARY_FILE

# Start the process
$NDDSHOME/bin/rtiwebintegrationservice -listeningPorts $PUBLIC_PORT -cfgFile ./xml_config/wis_service.xml -cfgName MotorControlWebApp -documentRoot $DOC_ROOT -enableKeepAlive yes -enableWebSockets
