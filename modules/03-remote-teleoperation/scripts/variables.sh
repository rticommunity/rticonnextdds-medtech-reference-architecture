##### Modify these variables for your environment

# Variables for all scenarios
# export NDDSHOME=<Connext installation path>
# export PUBLIC_ADDRESS=<public_IP_address> # Public IP address of the Passive side.
# export PUBLIC_PORT=<PUBLIC_PORT> # Public port on the Passive side (based on your static mapping)

# Variable for scenario 1 only
# export INTERNAL_PORT=<INTERNAL_PORT> # Public port on the Passive side (based on your static mapping).
                                       #Could be the same as `PUBLIC_PORT`. This variable is only used
                                       # by the _Passive_ Routing Service

export NDDSHOME=~/rti_connext_dds-7.3.0
export PUBLIC_ADDRESS=
export PUBLIC_PORT=10777

# Scenario 1 & 3 variables
export INTERNAL_PORT=10777
