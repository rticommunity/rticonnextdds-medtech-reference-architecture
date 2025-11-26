#!/bin/bash

# Self-signed CA
openssl req -nodes -x509 -days 1825 -text -sha256 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout ca/private/CaPrivateKey.pem -out ca/CaIdentity.pem -config ca/Ca.cnf

# Generate PrivateKeys and Identities
declare -A modules
modules[01-operating-room]="Arm ArmController Orchestrator PatientMonitor PatientSensor"
modules[02-record-playback]="RecordingService ReplayService"
modules[03-remote-teleoperation]="RsActive RsCloud RsPassive"

for module in "${!modules[@]}"; do
  for participant in ${modules[$module]}; do
    base="identities/$module/$participant/$participant"
    openssl req -nodes -new -newkey rsa:2048 -config "$base.cnf" -keyout "$base"PrivateKey.pem -out "$base.csr"
    openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in "$base.csr" -out "$base"Identity.pem
  done
done

# Sign Governance files for each domain and Permissions files for each DomainParticipant
declare -a xmls=(
  "GovernanceDomain0"
  "GovernanceDomain1"
  "01-operating-room/PermissionsArm"
  "01-operating-room/PermissionsArmController"
  "01-operating-room/PermissionsOrchestrator"
  "01-operating-room/PermissionsPatientMonitor"
  "01-operating-room/PermissionsPatientSensor"
  "02-record-playback/PermissionsRecordingService"
  "02-record-playback/PermissionsReplayService"
  "03-remote-teleoperation/PermissionsRsActive"
  "03-remote-teleoperation/PermissionsRsCloud"
  "03-remote-teleoperation/PermissionsRsPassive"
)

for xml in "${xmls[@]}"; do
  openssl smime -sign -in "xml/$xml.xml" -text -out "xml/signed/Signed${xml##*/}.p7s" -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
done

rm -f identities/*/*/*.csr
