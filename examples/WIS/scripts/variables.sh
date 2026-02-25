##### Modify these variables for your environment

# Variables for all scenarios
# export NDDSHOME=<Connext installation path>
# export PUBLIC_PORT=<PUBLIC_PORT> # Public port that the Web Integration Service will listen on.
# export DOC_ROOT=<DOC_ROOT>       # Document root for the Web Integration Service.


export PUBLIC_PORT=8080
export DOC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
#if not using bash, change the above line to:
#export DOC_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
