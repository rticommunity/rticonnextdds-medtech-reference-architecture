#!/bin/bash
# 
# (c) 2024 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# common.sh — shared environment setup for Module 04: Security Threat
# Source this file before launching threat applications.
# Usage: source ./scripts/common.sh

# Paths are relative to modules/04-security-threat/ working directory.
QOS_FILE="../../system_arch/qos/Qos.xml"
DOMAIN_LIBRARY_FILE="../../system_arch/xml_app_creation/DomainLibrary.xml"
THREAT_QOS_FILE="./xml_config/ThreatQos.xml"
THREAT_PARTICIPANT_LIBRARY_FILE="./xml_config/ThreatParticipantLibrary.xml"

# ThreatQos.xml must come before ThreatParticipantLibrary.xml so that the
# DpQosLib profiles are defined before the participant library references them.
export NDDS_QOS_PROFILES="${QOS_FILE};${DOMAIN_LIBRARY_FILE};${THREAT_QOS_FILE};${THREAT_PARTICIPANT_LIBRARY_FILE}"

# Default security artifact directories (can be overridden by environment)
export THREAT_SECURITY_ARTIFACTS_DIR="${THREAT_SECURITY_ARTIFACTS_DIR:-./security}"
export RTI_SECURITY_ARTIFACTS_DIR="${RTI_SECURITY_ARTIFACTS_DIR:-../../system_arch/security}"
