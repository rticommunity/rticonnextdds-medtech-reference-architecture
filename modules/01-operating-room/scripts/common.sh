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
DOMAIN_LIBRARY_FILE="../../system_arch/xml_app_creation/DomainLibrary.xml"
PARTICIPANT_LIBRARY_FILE="../../system_arch/xml_app_creation/ParticipantLibrary.xml"

export NDDS_QOS_PROFILES=$QOS_FILE";"$APPS_QOS_FILE";"$DOMAIN_LIBRARY_FILE";"$PARTICIPANT_LIBRARY_FILE

# If NDDSHOME is set, add the RTI Connext and bundled OpenSSL libraries to
# the dynamic library search path so the security plugin can be loaded.
# NOTE: On macOS, SIP strips DYLD_* variables from /bin/bash invocations,
# so we must set these inside the script rather than relying on the caller's
# environment.
if [ -n "${NDDSHOME:-}" ]; then
  # Add Connext lib/ (contains libnddssecurity, etc.)
  for _lib_dir in "$NDDSHOME"/lib/*/; do
    if [ -f "${_lib_dir}libnddsc.dylib" ] || [ -f "${_lib_dir}libnddsc.so" ]; then
      export DYLD_LIBRARY_PATH="${_lib_dir}${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
      export LD_LIBRARY_PATH="${_lib_dir}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      break
    fi
  done

  # Add bundled OpenSSL lib/ (contains libssl, libcrypto)
  for _ossl_dir in "$NDDSHOME"/third_party/openssl-*/; do
    for _arch_dir in "$_ossl_dir"*/; do
      if [ -d "${_arch_dir}release/lib" ]; then
        export DYLD_LIBRARY_PATH="${_arch_dir}release/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
        export LD_LIBRARY_PATH="${_arch_dir}release/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        break 2
      fi
    done
  done
fi