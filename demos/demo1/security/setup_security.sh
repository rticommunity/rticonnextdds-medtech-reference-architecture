# self-signed CA as the root of trust
openssl req -nodes -x509 -days 1825 -text -sha256 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout ca/private/CaKey.pem -out ca/CaCert.pem -config ca/Ca.cnf

# Identities for each participant

openssl req -nodes -new -newkey rsa:2048 -config identities/Arm/Arm.cnf -keyout identities/Arm/ArmKey.pem -out identities/Arm/Arm.csr
openssl x509 -req -days 730 -text -CA ca/CaCert.pem -CAkey ca/private/CaKey.pem -in identities/Arm/Arm.csr -out identities/Arm/Arm.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/ArmController/ArmController.cnf -keyout identities/ArmController/ArmControllerKey.pem -out identities/ArmController/ArmController.csr
openssl x509 -req -days 730 -text -CA ca/CaCert.pem -CAkey ca/private/CaKey.pem -in identities/ArmController/ArmController.csr -out identities/ArmController/ArmController.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/Orchestrator/Orchestrator.cnf -keyout identities/Orchestrator/OrchestratorKey.pem -out identities/Orchestrator/Orchestrator.csr
openssl x509 -req -days 730 -text -CA ca/CaCert.pem -CAkey ca/private/CaKey.pem -in identities/Orchestrator/Orchestrator.csr -out identities/Orchestrator/Orchestrator.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/PatientMonitor/PatientMonitor.cnf -keyout identities/PatientMonitor/PatientMonitorKey.pem -out identities/PatientMonitor/PatientMonitor.csr
openssl x509 -req -days 730 -text -CA ca/CaCert.pem -CAkey ca/private/CaKey.pem -in identities/PatientMonitor/PatientMonitor.csr -out identities/PatientMonitor/PatientMonitor.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/PatientSensor/PatientSensor.cnf -keyout identities/PatientSensor/PatientSensorKey.pem -out identities/PatientSensor/PatientSensor.csr
openssl x509 -req -days 730 -text -CA ca/CaCert.pem -CAkey ca/private/CaKey.pem -in identities/PatientSensor/PatientSensor.csr -out identities/PatientSensor/PatientSensor.pem

# Sign XML Files - governance & each participant's permissions

openssl smime -sign -in xml/Governance.xml -text -out xml/signed/signed_Governance.p7s -signer ca/CaCert.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_Arm.xml -text -out xml/signed/signed_Permissions_Arm.p7s -signer ca/CaCert.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_ArmController.xml -text -out xml/signed/signed_Permissions_ArmController.p7s -signer ca/CaCert.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_Orchestrator.xml -text -out xml/signed/signed_Permissions_Orchestrator.p7s -signer ca/CaCert.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_PatientMonitor.xml -text -out xml/signed/signed_Permissions_PatientMonitor.p7s -signer ca/CaCert.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_PatientSensor.xml -text -out xml/signed/signed_Permissions_PatientSensor.p7s -signer ca/CaCert.pem -inkey ca/private/CaKey.pem