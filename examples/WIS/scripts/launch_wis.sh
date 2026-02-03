#!/bin/bash

# Set up XML-related variables (QoS, XML App Creation, etc.)
source ./scripts/variables.sh

# Start the process
$NDDSHOME/bin/rtiwebintegrationservice -listeningPorts $PUBLIC_PORT -cfgFile ./xml_config/wis_service.xml -cfgName MotorControlWebApp -documentRoot $DOC_ROOT -enableKeepAlive yes -enableWebSockets
