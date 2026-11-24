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
"""Project-level security artifact status checks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "system" / "security" / "setup_security.py"


def test_operational_domain_secure_log_rule_precedes_wildcard(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    from setup_security import OPERATIONAL_DOMAIN

    expressions = [rule.topic_expression for rule in OPERATIONAL_DOMAIN.governance.topic_rules]
    assert expressions.index("DDS:Security:LogTopicV2") < expressions.index("*")


def test_arm_controller_can_receive_protected_device_status(monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    from setup_security import OPERATIONAL_DOMAIN

    controller = next(p for p in OPERATIONAL_DOMAIN.permissions if p.name == "ArmController")
    assert "t/device/status" in controller.subscribe_topics
    status_rule = next(
        rule
        for rule in OPERATIONAL_DOMAIN.governance.topic_rules
        if rule.topic_expression == "t/device/status"
    )
    assert status_rule.metadata_protection_kind == "ENCRYPT"
    root = PROJECT_ROOT / "system" / "security" / "domain_scope" / "OperationalDomain"
    permissions = ElementTree.parse(root / "permissions" / "ArmController" / "ArmController.xml")
    topics = [node.text for node in permissions.findall(".//subscribe/topics/topic")]
    assert "t/device/status" in topics
    governance = ElementTree.parse(
        root / "governance" / "OperationalDomain" / "OperationalDomain.xml"
    )
    rules = governance.findall(".//topic_rule")
    matching = next(
        rule for rule in rules if rule.findtext("topic_expression") == "t/device/status"
    )
    assert matching.findtext("metadata_protection_kind") == "ENCRYPT"


@pytest.mark.secure
def test_system_security_status_runs_clean() -> None:
    """Status report should run and not report expired artifacts."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--status", "-v"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    output = f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.returncode == 0, f"setup_security --status failed:\n{output}"
    assert "EXPIRED" not in output, f"Expired security artifacts detected:\n{output}"
