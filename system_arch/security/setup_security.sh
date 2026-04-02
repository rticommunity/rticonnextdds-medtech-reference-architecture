#!/bin/bash

# Use the OpenSSL bundled with RTI Connext (requires NDDSHOME to be set).
if [ -z "${NDDSHOME:-}" ]; then
  echo "Error: NDDSHOME must be set." >&2
  echo "  export NDDSHOME=/path/to/rti_connext_dds-<version>" >&2
  exit 1
fi

OPENSSL=""
for _ossl_dir in "$NDDSHOME"/third_party/openssl-*/; do
  for _arch_dir in "$_ossl_dir"*/; do
    if [ -x "${_arch_dir}release/bin/openssl" ]; then
      OPENSSL="${_arch_dir}release/bin/openssl"
      export DYLD_LIBRARY_PATH="${_arch_dir}release/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
      export LD_LIBRARY_PATH="${_arch_dir}release/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
      break 2
    fi
  done
done

if [ -z "$OPENSSL" ]; then
  echo "Error: Could not find OpenSSL under $NDDSHOME/third_party/" >&2
  exit 1
fi

echo "Using OpenSSL: $OPENSSL"

# Temporary extensions file for identity (end-entity) certificates.
# DDS Security requires keyUsage on identity certs.
IDENTITY_EXT=$(mktemp)
cat > "$IDENTITY_EXT" <<'EOF'
keyUsage = critical, digitalSignature
EOF
trap 'rm -f "$IDENTITY_EXT"' EXIT

# Self-signed CA
$OPENSSL req -nodes -x509 -days 1825 -text -sha256 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout ca/private/CaPrivateKey.pem -out ca/CaIdentity.pem -config ca/Ca.cnf -extensions v3_ca

# Generate PrivateKeys and Identities
generate_identities() {
  local module=$1
  shift
  for participant in "$@"; do
    base="identities/$module/$participant/$participant"
    $OPENSSL req -nodes -new -newkey rsa:2048 -config "$base.cnf" -keyout "$base"PrivateKey.pem -out "$base.csr"
    $OPENSSL x509 -req -days 730 -text -CAcreateserial -extfile "$IDENTITY_EXT" -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in "$base.csr" -out "$base"Identity.pem
  done
}

generate_identities "01-operating-room" Arm ArmController Orchestrator PatientMonitor PatientSensor SecureLogReader
generate_identities "02-record-playback" RecordingService ReplayService
generate_identities "03-remote-teleoperation" RsActive RsCloud RsPassive

# Sign Governance files for each domain and Permissions files for each DomainParticipant
declare -a xmls=(
  "GovernanceDomain0"
  "GovernanceDomain1"
  "01-operating-room/PermissionsArm"
  "01-operating-room/PermissionsArmController"
  "01-operating-room/PermissionsOrchestrator"
  "01-operating-room/PermissionsPatientMonitor"
  "01-operating-room/PermissionsPatientSensor"
  "01-operating-room/PermissionsSecureLogReader"
  "02-record-playback/PermissionsRecordingService"
  "02-record-playback/PermissionsReplayService"
  "03-remote-teleoperation/PermissionsRsActive"
  "03-remote-teleoperation/PermissionsRsCloud"
  "03-remote-teleoperation/PermissionsRsPassive"
)

for xml in "${xmls[@]}"; do
  $OPENSSL smime -sign -in "xml/$xml.xml" -text -out "xml/signed/Signed${xml##*/}.p7s" -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
done

rm -f identities/*/*/*.csr
