#!/bin/bash
# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# 
# setup_threat_security.sh
# 
# Generates all security artifacts for Module 04 - Security Threat.
# Must be run from the modules/04-security-threat/security/ directory.
#
# Prerequisite: system_arch/security/setup_security.sh must have been run first.
# The trusted CA private key at system_arch/security/ca/private/CaPrivateKey.pem
# and the trusted CA cert at system_arch/security/ca/CaIdentity.pem must exist.
#
# Usage:
#   cd modules/04-security-threat/security
#   ./setup_threat_security.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRUSTED_CA_DIR="$SCRIPT_DIR/../../../system_arch/security"

# Verify trusted CA artifacts exist (required for ForgedPerms and ExpiredCert modes)
if [ ! -f "$TRUSTED_CA_DIR/ca/CaIdentity.pem" ] || [ ! -f "$TRUSTED_CA_DIR/ca/private/CaPrivateKey.pem" ]; then
    echo "ERROR: Trusted CA artifacts not found at $TRUSTED_CA_DIR/ca/"
    echo "Please run system_arch/security/setup_security.sh first."
    exit 1
fi

echo "=== Generating Module 04 Security Artifacts ==="

# ─── 1. Rogue CA (self-signed) ────────────────────────────────────────────
echo "--- Generating Rogue CA..."
mkdir -p rogue_ca/private
openssl req -nodes -x509 -days 1825 -text -sha256 \
    -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
    -keyout rogue_ca/private/RogueCaPrivateKey.pem \
    -out rogue_ca/RogueCaIdentity.pem \
    -config rogue_ca/RogueCa.cnf

# ─── 2. RogueCA identities (signed by rogue CA) ───────────────────────────
echo "--- Generating Rogue CA identities..."
for participant in ThreatInjector ThreatExfiltrator; do
    base="identities/$participant/$participant"
    openssl req -nodes -new -newkey rsa:2048 \
        -config "$base.cnf" \
        -keyout "${base}PrivateKey.pem" \
        -out "${base}.csr"
    openssl x509 -req -days 730 -text \
        -CA rogue_ca/RogueCaIdentity.pem \
        -CAkey rogue_ca/private/RogueCaPrivateKey.pem \
        -CAcreateserial \
        -in "${base}.csr" \
        -out "${base}Identity.pem"
    rm -f "${base}.csr"
done

# Sign rogue-org permissions with rogue CA for RogueCA attack mode.
# These use subject names that match the rogue-CA-signed identity certs
# (O=Rogue Organization) rather than the legitimate org subject.
openssl smime -sign \
    -in "xml/PermissionsRogueCAInjector.xml" \
    -text \
    -out "identities/ThreatInjector/SignedPermissionsRogueCAInjector.p7s" \
    -signer rogue_ca/RogueCaIdentity.pem \
    -inkey rogue_ca/private/RogueCaPrivateKey.pem
openssl smime -sign \
    -in "xml/PermissionsRogueCAExfiltrator.xml" \
    -text \
    -out "identities/ThreatExfiltrator/SignedPermissionsRogueCAExfiltrator.p7s" \
    -signer rogue_ca/RogueCaIdentity.pem \
    -inkey rogue_ca/private/RogueCaPrivateKey.pem

# Sign governance with rogue CA (for RogueCA mode threat participant's own governance)
mkdir -p xml/signed
openssl smime -sign \
    -in "xml/GovernanceDomain0.xml" \
    -text \
    -out "xml/signed/SignedGovernanceDomain0RogueCA.p7s" \
    -signer rogue_ca/RogueCaIdentity.pem \
    -inkey rogue_ca/private/RogueCaPrivateKey.pem

# ─── 3. ForgedPerms identities (signed by TRUSTED CA) ────────────────────
echo "--- Generating ForgedPerms identities (trusted CA signed)..."
for participant in ThreatInjector ThreatExfiltrator; do
    base="forged_perms/$participant/$participant"
    openssl req -nodes -new -newkey rsa:2048 \
        -config "$base.cnf" \
        -keyout "${base}PrivateKey.pem" \
        -out "${base}.csr"
    openssl x509 -req -days 730 -text \
        -CA "$TRUSTED_CA_DIR/ca/CaIdentity.pem" \
        -CAkey "$TRUSTED_CA_DIR/ca/private/CaPrivateKey.pem" \
        -CAcreateserial \
        -in "${base}.csr" \
        -out "${base}Identity.pem"
    rm -f "${base}.csr"
done

# Sign permissions with ROGUE CA (this is the "forged" part — permissions signed by untrusted CA)
for participant in ThreatInjector ThreatExfiltrator; do
    openssl smime -sign \
        -in "xml/Permissions${participant}.xml" \
        -text \
        -out "forged_perms/${participant}/SignedPermissions${participant}.p7s" \
        -signer rogue_ca/RogueCaIdentity.pem \
        -inkey rogue_ca/private/RogueCaPrivateKey.pem
done

# ─── 4. Expired cert identities (signed by TRUSTED CA, notAfter in past) ──
echo "--- Generating Expired Certificate identities..."
# openssl x509 -req dropped -startdate/-enddate in OpenSSL 3.x (they became
# print-only flags).  openssl ca still supports both.  expired/ca.cnf uses
# relative paths so the database lives in expired/ itself alongside the certs.
export TRUSTED_CA_DIR
rm -f expired/index.txt expired/index.txt.attr expired/serial
touch expired/index.txt
echo 1000 > expired/serial
mkdir -p expired/newcerts

for participant in ThreatInjector ThreatExfiltrator; do
    base="expired/$participant/${participant}Expired"
    openssl req -nodes -new -newkey rsa:2048 \
        -config "$base.cnf" \
        -keyout "expired/${participant}/${participant}PrivateKey.pem" \
        -out "${base}.csr"
    openssl ca -batch \
        -config "expired/ca.cnf" \
        -startdate 20200101000000Z \
        -enddate   20220101000000Z \
        -in  "${base}.csr" \
        -out "${base}Identity.pem"
    rm -f "${base}.csr"
done

# Sign permissions with trusted CA for ExpiredCert mode
for participant in ThreatInjector ThreatExfiltrator; do
    openssl smime -sign \
        -in "xml/Permissions${participant}.xml" \
        -text \
        -out "expired/${participant}/SignedPermissions${participant}.p7s" \
        -signer "$TRUSTED_CA_DIR/ca/CaIdentity.pem" \
        -inkey "$TRUSTED_CA_DIR/ca/private/CaPrivateKey.pem"
done

# Sign governance with trusted CA (for ForgedPerms and ExpiredCert modes)
openssl smime -sign \
    -in "xml/GovernanceDomain0.xml" \
    -text \
    -out "xml/signed/SignedGovernanceDomain0.p7s" \
    -signer "$TRUSTED_CA_DIR/ca/CaIdentity.pem" \
    -inkey "$TRUSTED_CA_DIR/ca/private/CaPrivateKey.pem"

echo "=== Security artifact generation complete ==="
echo ""
echo "Generated artifacts:"
echo "  rogue_ca/RogueCaIdentity.pem                          (self-signed rogue CA)"
echo "  identities/ThreatInjector/ThreatInjectorIdentity.pem  (rogue-CA-signed)"
echo "  identities/ThreatExfiltrator/ThreatExfiltratorIdentity.pem (rogue-CA-signed)"
echo "  forged_perms/ThreatInjector/ThreatInjectorIdentity.pem     (trusted-CA-signed)"
echo "  forged_perms/ThreatInjector/SignedPermissionsThreatInjector.p7s (rogue-CA-signed!)"
echo "  expired/ThreatInjector/ThreatInjectorExpiredIdentity.pem    (trusted-CA-signed, EXPIRED)"
echo "  xml/signed/SignedGovernanceDomain0.p7s                (trusted-CA-signed)"
echo "  xml/signed/SignedGovernanceDomain0RogueCA.p7s         (rogue-CA-signed)"
