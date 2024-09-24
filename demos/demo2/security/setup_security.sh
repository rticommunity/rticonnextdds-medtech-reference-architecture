# Identities for each participant

openssl req -nodes -new -newkey rsa:2048 -config identities/RecordingService/RecordingService.cnf -keyout identities/RecordingService/RecordingServiceKey.pem -out identities/RecordingService/RecordingService.csr
openssl x509 -req -days 730 -text -CA ../../demo1/security/ca/CaCert.pem -CAkey ../../demo1/security/ca/private/CaKey.pem -in identities/RecordingService/RecordingService.csr -out identities/RecordingService/RecordingService.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/ReplayService/ReplayService.cnf -keyout identities/ReplayService/ReplayServiceKey.pem -out identities/ReplayService/ReplayService.csr
openssl x509 -req -days 730 -text -CA ../../demo1/security/ca/CaCert.pem -CAkey ../../demo1/security/ca/private/CaKey.pem -in identities/ReplayService/ReplayService.csr -out identities/ReplayService/ReplayService.pem

# Sign XML Files - governance & each participant's permissions

openssl smime -sign -in xml/Permissions_RecordingService.xml -text -out xml/signed/signed_Permissions_RecordingService.p7s -signer ../../demo1/security/ca/CaCert.pem -inkey ../../demo1/security/ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_ReplayService.xml -text -out xml/signed/signed_Permissions_ReplayService.p7s -signer ../../demo1/security/ca/CaCert.pem -inkey ../../demo1/security/ca/private/CaKey.pem