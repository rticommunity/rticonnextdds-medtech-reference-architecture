#!/bin/bash
# Remember to source the .bash file to dynamically load the security libraries

# Store the "-s" argument if provided
SEC_FLAG=${1:-}

# Set up XML-related variables (QoS, XML App Creation, etc.)
source ./scripts/common.sh $SEC_FLAG

# Start the processes
python3 src/xbox_controller.py &
