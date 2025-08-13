# Self-signed CA as the root of trust for all demos
openssl req -nodes -x509 -days 1825 -text -sha256 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout ca/private/CaPrivateKey.pem -out ca/CaIdentity.pem -config ca/Ca.cnf

# Identities for each participant

# Demo1
openssl req -nodes -new -newkey rsa:2048 -config identities/demo1/Arm/Arm.cnf -keyout identities/demo1/Arm/ArmPrivateKey.pem -out identities/demo1/Arm/Arm.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo1/Arm/Arm.csr -out identities/demo1/Arm/ArmIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo1/ArmController/ArmController.cnf -keyout identities/demo1/ArmController/ArmControllerPrivateKey.pem -out identities/demo1/ArmController/ArmController.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo1/ArmController/ArmController.csr -out identities/demo1/ArmController/ArmControllerIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo1/Orchestrator/Orchestrator.cnf -keyout identities/demo1/Orchestrator/OrchestratorPrivateKey.pem -out identities/demo1/Orchestrator/Orchestrator.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo1/Orchestrator/Orchestrator.csr -out identities/demo1/Orchestrator/OrchestratorIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo1/PatientMonitor/PatientMonitor.cnf -keyout identities/demo1/PatientMonitor/PatientMonitorPrivateKey.pem -out identities/demo1/PatientMonitor/PatientMonitor.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo1/PatientMonitor/PatientMonitor.csr -out identities/demo1/PatientMonitor/PatientMonitorIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo1/PatientSensor/PatientSensor.cnf -keyout identities/demo1/PatientSensor/PatientSensorPrivateKey.pem -out identities/demo1/PatientSensor/PatientSensor.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo1/PatientSensor/PatientSensor.csr -out identities/demo1/PatientSensor/PatientSensorIdentity.pem

# Demo2
openssl req -nodes -new -newkey rsa:2048 -config identities/demo2/RecordingService/RecordingService.cnf -keyout identities/demo2/RecordingService/RecordingServicePrivateKey.pem -out identities/demo2/RecordingService/RecordingService.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo2/RecordingService/RecordingService.csr -out identities/demo2/RecordingService/RecordingServiceIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo2/ReplayService/ReplayService.cnf -keyout identities/demo2/ReplayService/ReplayServicePrivateKey.pem -out identities/demo2/ReplayService/ReplayService.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo2/ReplayService/ReplayService.csr -out identities/demo2/ReplayService/ReplayServiceIdentity.pem

# Demo3
openssl req -nodes -new -newkey rsa:2048 -config identities/demo3/RsActive/RsActive.cnf -keyout identities/demo3/RsActive/RsActivePrivateKey.pem -out identities/demo3/RsActive/RsActive.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo3/RsActive/RsActive.csr -out identities/demo3/RsActive/RsActiveIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo3/RsCloud/RsCloud.cnf -keyout identities/demo3/RsCloud/RsCloudPrivateKey.pem -out identities/demo3/RsCloud/RsCloud.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo3/RsCloud/RsCloud.csr -out identities/demo3/RsCloud/RsCloudIdentity.pem
openssl req -nodes -new -newkey rsa:2048 -config identities/demo3/RsPassive/RsPassive.cnf -keyout identities/demo3/RsPassive/RsPassivePrivateKey.pem -out identities/demo3/RsPassive/RsPassive.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaPrivateKey.pem -in identities/demo3/RsPassive/RsPassive.csr -out identities/demo3/RsPassive/RsPassiveIdentity.pem


# Sign XML Files - Governance file & each DP's permissions

openssl smime -sign -in xml/GovernanceDomain0.xml -text -out xml/signed/SignedGovernanceDomain0.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/GovernanceDomain1.xml -text -out xml/signed/SignedGovernanceDomain1.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo1/PermissionsArm.xml -text -out xml/signed/SignedPermissionsArm.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo1/PermissionsArmController.xml -text -out xml/signed/SignedPermissionsArmController.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo1/PermissionsOrchestrator.xml -text -out xml/signed/SignedPermissionsOrchestrator.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo1/PermissionsPatientMonitor.xml -text -out xml/signed/SignedPermissionsPatientMonitor.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo1/PermissionsPatientSensor.xml -text -out xml/signed/SignedPermissionsPatientSensor.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo2/PermissionsRecordingService.xml -text -out xml/signed/SignedPermissionsRecordingService.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo2/PermissionsReplayService.xml -text -out xml/signed/SignedPermissionsReplayService.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo3/PermissionsRsActive.xml -text -out xml/signed/SignedPermissionsRsActive.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo3/PermissionsRsCloud.xml -text -out xml/signed/SignedPermissionsRsCloud.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem
openssl smime -sign -in xml/demo3/PermissionsRsPassive.xml -text -out xml/signed/SignedPermissionsRsPassive.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaPrivateKey.pem

# Deleting unnecessary files
rm -f identities/*/*.csr


