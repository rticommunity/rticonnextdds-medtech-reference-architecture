#!/bin/bash
# Remember to source the .bash file to dynamically load the security libraries

# Store the "-s" argument if provided
SEC_FLAG=${1:-}

# Set up XML-related variables (QoS, XML App Creation, etc.)
source ./scripts/variables.sh

# Apply Security QoS if needed
if [ "$SEC_FLAG" = "-s" ]; then
  echo "Launching CDS with Security..."
  CFG_NAME=CdsConfigCloudSecurity
elif [ -z "$SEC_FLAG" ]; then
  echo "Launching CDS without Security..."
  CFG_NAME=CdsConfigCloud
else
  echo "Unknown argument: $SEC_FLAG. Use -s to run with Security. Don't use any argument to run without security"
  exit 1
fi

# Start the processes
$NDDSHOME/bin/rticlouddiscoveryservice -cfgFile ./xml_config/CdsConfigCloud.xml -cfgName $CFG_NAME