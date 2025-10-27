#!/bin/bash

# Self-signed CA
openssl req -nodes -x509 -days 1825 -text -sha256 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout ca/private/CaPrivateKey.pem -out ca/CaIdentity.pem -config ca/Ca.cnf

# Generate PrivateKeys and Identities
declare -A demos
demos[demo1]="Arm ArmController Orchestrator PatientMonitor PatientSensor"
demos[demo2]="RecordingService ReplayService"
demos[demo3]="RsActive RsCloud RsPassive"

for demo in "${!demos[@]}"; do
  for participant in ${demos[$demo]}; do
    base="identities/$demo/$participant/$participant"
    openssl req -nodes -new -newkey rsa:2048 -config "$base.cnf" -keyout "$base"PrivateKey.pem -out "$base.csr"
    openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in "$base.csr" -out "$base"Identity.pem
  done
done

# Sign Governance files for each domain and Permissions files for each DomainParticipant
declare -a xmls=(
  "GovernanceDomain0"
  "GovernanceDomain1"
  "demo1/PermissionsArm"
  "demo1/PermissionsArmController"
  "demo1/PermissionsOrchestrator"
  "demo1/PermissionsPatientMonitor"
  "demo1/PermissionsPatientSensor"
  "demo2/PermissionsRecordingService"
  "demo2/PermissionsReplayService"
  "demo3/PermissionsRsActive"
  "demo3/PermissionsRsCloud"
  "demo3/PermissionsRsPassive"
)

for xml in "${xmls[@]}"; do
  openssl smime -sign -in "xml/$xml.xml" -text -out "xml/signed/Signed${xml##*/}.p7s" -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
done

rm -f identities/*/*/*.csr
