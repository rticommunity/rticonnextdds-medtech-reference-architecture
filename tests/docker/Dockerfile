#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS.  Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software.  RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

# ==========================================================================
# RTI MedTech Reference Architecture — Multi-stage Dockerfile
#
# Stages:
#   connext-base  — Ubuntu 24.04 + Connext DDS via apt
#   build-base    — Python + C++ dependencies
#   build         — CMake configure + build + security artifacts
#   test          — Pytest for headless browser-mode testing
#
# RTI license file is NOT baked into the image.
# Mount it at runtime via -v:
#   docker run --rm \
#     -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
#     medtech-test
#
# Build targets (from repo root):
#   docker build -f tests/docker/Dockerfile --target build -t medtech-build .
#   docker build -f tests/docker/Dockerfile --target test  -t medtech-test .
#
# Run all tests:
#   docker run --rm \
#     -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
#     medtech-test
#
# Run specific tests:
#   docker run --rm \
#     -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.7.0/rti_license.dat:ro \
#     medtech-test pytest modules/01-operating-room/tests/test_types.py -v
# ==========================================================================

# Shared build args (global defaults).
ARG CONNEXT_VERSION=7.7.0
ARG PYTHON_VERSION=3.11

# ------------------------------------------------------------------
# Stage 1: Connext base
# ------------------------------------------------------------------
FROM ubuntu:24.04 AS connext-base

ARG CONNEXT_VERSION
ARG DEBIAN_FRONTEND=noninteractive

ENV CONNEXT_VERSION=${CONNEXT_VERSION}
ENV NDDSHOME=/opt/rti.com/rti_connext_dds-${CONNEXT_VERSION}
ENV PATH=${NDDSHOME}/bin:${PATH}
ENV RTI_LICENSE_FILE=/opt/rti.com/rti_license.dat

# System packages (keep layer small by cleaning up)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
        cmake g++ make pkg-config \
        git \
    && rm -rf /var/lib/apt/lists/*

# RTI apt repository
RUN curl -sSL -o /usr/share/keyrings/rti-official-archive.gpg \
        https://packages.rti.com/deb/official/repo.key \
    && printf "deb [arch=%s signed-by=%s] %s %s main\n" \
        "$(dpkg --print-architecture)" \
        "/usr/share/keyrings/rti-official-archive.gpg" \
        "https://packages.rti.com/deb/official" \
        "$(. /etc/os-release && echo ${VERSION_CODENAME})" \
        > /etc/apt/sources.list.d/rti-official.list \
    && apt-get update

# Install Connext DDS (accept license non-interactively)
RUN echo "rti-connext-dds-${CONNEXT_VERSION}-common rti-connext-dds-${CONNEXT_VERSION}/license/accepted select true" \
        | debconf-set-selections \
    && apt-get install -y --no-install-recommends \
    rti-connext-dds-${CONNEXT_VERSION}-lib-dev \
    rti-connext-dds-${CONNEXT_VERSION}-rtiddsgen \
    rti-connext-dds-${CONNEXT_VERSION}-services-all \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# Stage 2: Build C++ modules + security artifacts
# ------------------------------------------------------------------
FROM connext-base AS build-base

ARG PYTHON_VERSION

# System packages (keep layer small by cleaning up)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
        cmake g++ make pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Python packages (enable deadsnakes for broader PYTHON_VERSION support)
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
    && rm -rf /var/lib/apt/lists/*

# Create venv and install dependencies needed by build and test workflows.
ENV VIRTUAL_ENV=/workspace/.venv
RUN python${PYTHON_VERSION} -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

WORKDIR /workspace
COPY requirements*.txt ./

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        rti.connext~=${CONNEXT_VERSION}.0 \
        -r requirements-dev.txt

# ------------------------------------------------------------------
# Stage 3: Build C++ modules + security artifacts
# ------------------------------------------------------------------
FROM build-base AS build

WORKDIR /workspace
COPY . .

# Build project with CMake
RUN eval $(rtienv) && python${PYTHON_VERSION} build.py -DRTICONNEXTDDS_VERSION=${CONNEXT_VERSION} -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=ON

# Generate security artifacts (certificates, signed governance/permissions)
RUN python${PYTHON_VERSION} system/security/setup_security.py --force
RUN python${PYTHON_VERSION} modules/04-security-threat/security/setup_threat_security.py --force

# ------------------------------------------------------------------
# Stage 4: Test environment
# ------------------------------------------------------------------
FROM build AS test

ARG DEBIAN_FRONTEND=noninteractive

WORKDIR /workspace

COPY tests/docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["entrypoint.sh"]

# Default: run all tests with verbose output
CMD ["-v"]
