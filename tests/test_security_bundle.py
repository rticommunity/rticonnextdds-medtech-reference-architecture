# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

"""Test local bundle publication without touching the operator's workspace."""

import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ISSUER = PROJECT / "system" / "security" / "setup_security.py"


def test_local_runtime_bundle(tmp_path):
    workspace = tmp_path / "issued"
    artifacts = tmp_path / "runtime"
    base = [sys.executable, str(ISSUER), "--workspace", str(workspace)]
    stage = [*base, "--stage", "--artifacts", str(artifacts), "--deployment", "demo"]

    subprocess.run(
        [*base, "--connext-version", "7.7.0", "--strict"],
        check=True,
        capture_output=True,
    )
    subprocess.run(stage, check=True, capture_output=True)
    role = artifacts / "0" / "demo" / "PatientSensor"
    assert {path.name for path in role.iterdir()} == {
        "identity.crt",
        "identity.key",
        "permissions.p7s",
    }
    assert (artifacts / "1" / "demo" / "RsActiveWan" / "permissions.p7s").is_file()
    assert not (artifacts / "ca").exists()
    assert (artifacts / "0" / "psk_secret.key").read_bytes() != (
        artifacts / "1" / "psk_secret.key"
    ).read_bytes()
    assert b"Already staged" in subprocess.check_output(stage)

    active_key = (role / "identity.key").read_bytes()
    issued_keys = workspace.glob("identity/**/private/PatientSensor.key")
    next(issued_keys).write_text("invalid key", encoding="utf-8")
    assert subprocess.run(stage, capture_output=True).returncode != 0
    candidate = tmp_path / "candidate"
    assert (
        subprocess.run([*stage, "--artifacts", str(candidate)], capture_output=True).returncode != 0
    )
    assert not candidate.exists()
    assert (role / "identity.key").read_bytes() == active_key
