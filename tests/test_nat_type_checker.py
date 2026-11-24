#
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the software solely for use with RTI Connext DDS. Licensee may
# redistribute copies of the software provided that all such copies are
# subject to this license. The software is provided "as is", with no warranty
# of any type, including any warranty for fitness for any purpose. RTI is
# under no obligation to maintain or support the software. RTI shall not be
# liable for any incidental or consequential damages arising out of the use or
# inability to use the software.

import pytest
import stun

from tools.nat_type_checker import nat_type_checker


@pytest.mark.parametrize(
    ("nat_type", "expected"),
    [
        (stun.FullCone, "including a peer behind another NAT type"),
        (stun.RestricNAT, "also behind a cone NAT"),
        (stun.RestricPortNAT, "also behind a cone NAT"),
        (stun.SymmetricNAT, "full-cone peer"),
    ],
)
def test_stun_results_are_advisory(monkeypatch, capsys, nat_type, expected):
    monkeypatch.setattr(stun, "get_nat_type", lambda *args: (nat_type, {}))

    assert nat_type_checker.main() == 0
    output = capsys.readouterr().out
    assert expected in output
    assert "not proof of NAT type or reachability" in output
    assert "both endpoints" in output


@pytest.mark.parametrize("nat_type", [stun.Blocked, stun.ChangedAddressError, "unrecognized"])
def test_unknown_stun_results_are_inconclusive(monkeypatch, capsys, nat_type):
    monkeypatch.setattr(stun, "get_nat_type", lambda *args: (nat_type, {}))

    assert nat_type_checker.main() == 1
    output = capsys.readouterr().out
    assert "inconclusive" in output
    assert "Scenario 3" in output


def test_probe_failure_is_explicit(monkeypatch, capsys):
    def fail(*args):
        raise OSError("test STUN failure")

    monkeypatch.setattr(stun, "get_nat_type", fail)
    assert nat_type_checker.main() == 1
    output = capsys.readouterr().out
    assert "test STUN failure" in output
    assert "inconclusive" in output
