# ==========================================================================
# RTI MedTech Reference Architecture — Multi-stage Dockerfile
#
# Stages:
#   connext-base  — Ubuntu 22.04 + Connext DDS via apt
#   build         — CMake configure + build + security artifacts
#   test          — Python venv, pytest, Xvfb for headless testing
#
# RTI license file is NOT baked into the image.
# Mount it at runtime via -v:
#   docker run --rm \
#     -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro \
#     medtech-test
#
# Build targets (from repo root):
#   docker build -f tests/docker/Dockerfile --target build -t medtech-build .
#   docker build -f tests/docker/Dockerfile --target test  -t medtech-test .
#
# Run all tests:
#   docker run --rm \
#     -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro \
#     medtech-test
#
# Run specific tests:
#   docker run --rm \
#     -v $RTI_LICENSE_FILE:/opt/rti.com/rti_connext_dds-7.3.1/rti_license.dat:ro \
#     medtech-test python -m pytest modules/01-operating-room/tests/test_types.py -v
# ==========================================================================

# ------------------------------------------------------------------
# Stage 1: Connext base
# ------------------------------------------------------------------
FROM ubuntu:22.04 AS connext-base

ARG CONNEXT_VERSION=7.3.1
ARG OPENSSL_VERSION=3.5.5
ARG CONNEXTDDS_ARCH=x64Linux4gcc7.3.0
ARG DEBIAN_FRONTEND=noninteractive

ENV CONNEXT_VERSION=${CONNEXT_VERSION}
ENV OPENSSL_VERSION=${OPENSSL_VERSION}
ENV NDDSHOME=/opt/rti.com/rti_connext_dds-${CONNEXT_VERSION}
ENV CONNEXTDDS_ARCH=${CONNEXTDDS_ARCH}
ENV PATH=${NDDSHOME}/bin:${PATH}

# System packages (keep layer small by cleaning up)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg \
        cmake g++ make pkg-config \
        libgtkmm-3.0-dev \
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
    && apt-get install -y --no-install-recommends rti-connext-dds-${CONNEXT_VERSION} \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------------
# Stage 2: Build C++ modules + security artifacts
# ------------------------------------------------------------------
FROM connext-base AS build

WORKDIR /workspace
COPY . .

# Build project with CMake
RUN python3 build.py

# Generate security artifacts (certificates, signed governance/permissions)
RUN python3 system_arch/security/setup_security.py
RUN python3 modules/04-security-threat/security/setup_threat_security.py

# ------------------------------------------------------------------
# Stage 3: Test environment
# ------------------------------------------------------------------
FROM build AS test

ARG DEBIAN_FRONTEND=noninteractive

# Python 3.9 via deadsnakes PPA (matches advertised minimum version)
RUN apt-get update && apt-get install -y --no-install-recommends software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.9 python3.9-venv python3.9-dev \
        xvfb \
        libegl1 libxkbcommon0 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js 18 LTS from NodeSource (system nodejs is too old)
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create venv and install dependencies from requirements-dev.txt
ENV VIRTUAL_ENV=/workspace/.venv
RUN python3.9 -m venv ${VIRTUAL_ENV}
ENV PATH=${VIRTUAL_ENV}/bin:${PATH}

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        rti.connext==${CONNEXT_VERSION} \
        -r requirements-dev.txt

RUN npm install -g markdownlint-cli

# Runtime library paths: Connext libs + bundled OpenSSL (for security plugin)
ENV LD_LIBRARY_PATH=${NDDSHOME}/lib/${CONNEXTDDS_ARCH}:${NDDSHOME}/third_party/openssl-${OPENSSL_VERSION}/${CONNEXTDDS_ARCH}/release/lib

# Qt needs a display; Xvfb provides a virtual one
ENV QT_QPA_PLATFORM=offscreen
ENV DISPLAY=:99

WORKDIR /workspace

# Default: run all tests headlessly
CMD ["bash", "-lc", "Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp & xvfb_pid=$!; trap 'kill ${xvfb_pid}' EXIT; tests/run_tests.sh -v"]
