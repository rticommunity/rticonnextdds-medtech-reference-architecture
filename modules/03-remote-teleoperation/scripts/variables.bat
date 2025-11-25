:: Modify these variables for your environment

:: Variables for all scenarios
:: set NDDSHOME=<Connext installation path>
:: set PUBLIC_ADDRESS=<public_IP_address>   :: Public IP address of the Passive side.
:: set PUBLIC_PORT=<PUBLIC_PORT>            :: Public port on the Passive side (based on your static mapping)

:: Variable for scenario 1 only
:: set INTERNAL_PORT=<INTERNAL_PORT>        :: Public port on the Passive side (based on your static mapping).
                                            :: Could be the same as PUBLIC_PORT. This variable is only used
                                            :: by the Passive Routing Service

set NDDSHOME="C:\Program Files\rti_connext_dds-7.3.0"
set PUBLIC_ADDRESS=
set PUBLIC_PORT=10777

:: Scenario 1 & 3 variables
set INTERNAL_PORT=10777