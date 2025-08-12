# self-signed CA as the root of trust
openssl req -nodes -x509 -days 1825 -text -sha256 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout ca/private/CaKey.pem -out ca/CaIdentity.pem -config ca/Ca.cnf

# Identities for each participant

openssl req -nodes -new -newkey rsa:2048 -config identities/RsActive/RsActive.cnf -keyout identities/RsActive/RsActivePrivateKey.pem -out identities/RsActive/RsActive.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaKey.pem -in identities/RsActive/RsActive.csr -out identities/RsActive/RsActiveIdentity.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/RsCloud/RsCloud.cnf -keyout identities/RsCloud/RsCloudPrivateKey.pem -out identities/RsCloud/RsCloud.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaKey.pem -in identities/RsCloud/RsCloud.csr -out identities/RsCloud/RsCloudIdentity.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/RsLocal/RsLocal.cnf -keyout identities/RsLocal/RsLocalPrivateKey.pem -out identities/RsLocal/RsLocal.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaKey.pem -in identities/RsLocal/RsLocal.csr -out identities/RsLocal/RsLocalIdentity.pem

openssl req -nodes -new -newkey rsa:2048 -config identities/RsPassive/RsPassive.cnf -keyout identities/RsPassive/RsPassivePrivateKey.pem -out identities/RsPassive/RsPassive.csr
openssl x509 -req -days 730 -text -CA ca/CaIdentity.pem -CAkey ca/private/CaKey.pem -in identities/RsPassive/RsPassive.csr -out identities/RsPassive/RsPassiveIdentity.pem

# Sign XML Files - governance & each participant's permissions

openssl smime -sign -in xml/Governance.xml -text -out xml/signed/signed_Governance.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_RsActive.xml -text -out xml/signed/signed_Permissions_RsActive.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_RsCloud.xml -text -out xml/signed/signed_Permissions_RsCloud.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_RsLocal.xml -text -out xml/signed/signed_Permissions_RsLocal.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaKey.pem
openssl smime -sign -in xml/Permissions_RsPassive.xml -text -out xml/signed/signed_Permissions_RsPassive.p7s -signer ca/CaIdentity.pem -inkey ca/private/CaKey.pem