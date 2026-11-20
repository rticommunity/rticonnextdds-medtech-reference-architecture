# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.medtech import medtech_cli, module_runner
from tools.medtech.providers import eps

ROOT = Path(__file__).resolve().parents[1]


def test_help_and_scenario_list_need_no_environment():
    env = {k: v for k, v in os.environ.items() if k not in ("NDDSHOME", "CONNEXTDDS_ARCH")}
    for args, text in [(["--help"], "setup"), (["run", "--list-scenarios"], "or-all")]:
        result = subprocess.run(
            [sys.executable, "-IS", str(ROOT / "medtech.py"), *args],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        assert text in result.stdout


def test_up_selects_gamepad_without_arm_and_stops_on_setup_failure(monkeypatch):
    def fail_setup(extras):
        assert extras == {"gamepad"}
        raise subprocess.CalledProcessError(17, ["uv"])

    def unexpected(*args, **kwargs):
        pytest.fail("A later stage ran after setup failed")

    monkeypatch.setattr(medtech_cli, "setup", fail_setup)
    monkeypatch.setattr(medtech_cli, "run_command", unexpected)
    monkeypatch.setattr(medtech_cli.build, "run_build", unexpected)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "medtech.py",
            "up",
            "01-operating-room",
            "ArmController",
            "--variant",
            "ArmController=xbox",
        ],
    )
    assert medtech_cli.main() == 17


def test_security_plan_remembers_only_provider(monkeypatch, tmp_path, capsys):
    settings = tmp_path / ".medtech" / "settings.toml"
    monkeypatch.setattr(medtech_cli, "SETTINGS", settings)
    monkeypatch.setattr(
        sys, "argv", ["medtech.py", "security", "plan", "--provider", "local", "--save"]
    )
    assert medtech_cli.provider_choice() == "local"
    assert medtech_cli.main() == 0
    assert settings.read_text() == 'provider = "local"\n'
    assert "setup_security.py --stage" in capsys.readouterr().out
    settings.write_text('provider = "medcrypt"\n')
    with pytest.raises(ValueError, match="Unsupported security provider 'medcrypt'"):
        medtech_cli.provider_choice()
    assert medtech_cli.provider_choice("local") == "local"


@pytest.mark.parametrize("command", ["run", "up"])
def test_secure_launch_uses_selected_provider_bundle(command, monkeypatch, tmp_path):
    settings = tmp_path / "settings.toml"
    settings.write_text('provider = "local"\n')
    monkeypatch.setattr(medtech_cli, "SETTINGS", settings)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(
        medtech_cli.SECURITY_PROVIDERS,
        "test-provider",
        medtech_cli.SecurityProvider(("Prepare separately.",), lambda: (Path("ready"), "demo")),
    )
    bundle = tmp_path / "ready"
    role = bundle / "0/demo/PatientSensor"
    role.mkdir(parents=True)
    for name in ("identity.crt", "identity.key", "permissions.p7s"):
        (role / name).write_text("present")
    for name in ("identity_ca.crt", "permissions_ca.crt", "governance.p7s", "psk_secret.key"):
        (bundle / "0" / name).write_text("present")
    specs = [([["/example/PatientSensor"]], ROOT / "modules/01-operating-room", {})]
    monkeypatch.setattr(medtech_cli.launch, "launch_selection", lambda args: specs)
    monkeypatch.setattr(medtech_cli, "preflight_apps", lambda *args: None)

    def explain(resolved, *, explain):
        assert explain
        assert resolved[0][2]["RTI_SECURITY_ARTIFACTS_DIR"] == str(bundle)
        assert resolved[0][2]["RTI_SECURITY_DEPLOYMENT_NAME"] == "demo"
        return 0

    monkeypatch.setattr(module_runner, "launch_multi", explain)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "medtech.py",
            command,
            "01-operating-room",
            "PatientSensor",
            "--security",
            "--provider",
            "test-provider",
            "--explain",
        ],
    )
    assert medtech_cli.main() == 0


@pytest.mark.parametrize("event", ["later-failure", "spawn-failure", "clean-exit"])
def test_supervision_handles_independent_child_outcomes(event, monkeypatch, tmp_path):
    children = []
    popen = subprocess.Popen

    def record(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(module_runner.subprocess, "Popen", record)
    first = [sys.executable, "-c", "import time; time.sleep(8)"]
    second = [sys.executable, "-c", "raise SystemExit(29)"]
    if event == "spawn-failure":
        second = [str(tmp_path / "does-not-exist")]
    if event == "clean-exit":
        first = [sys.executable, "-c", "import time; time.sleep(0.15)"]
        second = [sys.executable, "-c", "pass"]
    specs = [([first, second], tmp_path, os.environ.copy())]
    if event == "spawn-failure":
        with pytest.raises(OSError):
            module_runner.launch_multi(specs)
    else:
        assert module_runner.launch_multi(specs) == (29 if event == "later-failure" else 0)
    assert children and all(child.poll() is not None for child in children)
    if event != "clean-exit":
        assert children[0].returncode != 0


def test_command_trace_redacts_sensitive_values(tmp_path, capsys):
    module_runner.print_command(
        ["tool", "--password", "hidden-1", "-DAPI_KEY:STRING=hidden-2", "--safe", "shown"],
        tmp_path,
        {"DEMO_TOKEN": "hidden-3"},
    )
    trace = capsys.readouterr().out
    assert "hidden-" not in trace
    assert all(value in trace for value in (str(tmp_path), "--safe", "shown", "DEMO_TOKEN"))


def test_secure_preflight_rejects_empty_artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("RTI_SECURITY_ARTIFACTS_DIR", str(tmp_path))
    specs = [([["/example/PatientSensor"]], ROOT / "modules" / "01-operating-room", {})]
    with pytest.raises(ValueError, match=r"Incomplete security bundle.*PatientSensor"):
        medtech_cli.check_security(specs, "local")
    assert not list(tmp_path.iterdir()), "Preflight must not provision credentials"


@pytest.fixture
def eps_bundle(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDTECH_EPS_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("MEDTECH_EPS_DEPLOYMENT_NAME", "station")
    monkeypatch.setenv("MEDTECH_EPS_DOMAIN_TAG", "or")
    domain = tmp_path / "0.or"
    for path in (
        "identity_ca.crt",
        "permissions_ca.crt",
        "governance.p7s",
        "psk_secret.key",
        "psk_secret_extra.key",
        "crl.pem",
        "station/Orchestrator/identity.crt",
        "station/Orchestrator/identity.key",
        "station/Orchestrator/permissions.p7s",
        "station/SecureLogReader/identity.crt",
        "station/SecureLogReader/identity.key",
        "station/SecureLogReader/permissions.p7s",
    ):
        dest = domain / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("test artifact")
    return domain


def test_eps_launch_checks_nested_log_reader_before_setup(monkeypatch, eps_bundle, caplog):
    (eps_bundle / "station/SecureLogReader/identity.key").write_text("")
    monkeypatch.setattr(medtech_cli, "setup", lambda _: pytest.fail("Setup ran before EPS check"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "medtech.py",
            "up",
            "01-operating-room",
            "Orchestrator",
            "--security",
            "--provider",
            "eps",
        ],
    )
    assert medtech_cli.main() == 1
    assert "0.or/station/SecureLogReader/identity.key" in caplog.text


def test_eps_launch_resolves_selected_roles_only(eps_bundle):
    env = eps.launch_environment([("01-operating-room", ["Orchestrator"])])
    assert env["RTI_SECURITY_ARTIFACTS_DIR"] == str(eps_bundle.parent)
    assert env["RTI_SECURITY_LAN_DOMAIN_DIR"] == "0.or"
    assert env["RTI_SECURITY_DEPLOYMENT_NAME"] == "station"
    with pytest.raises(ValueError, match="Use local for Module 04"):
        eps.launch_environment([("01-operating-room", None), ("04-security-threat", None)])


def test_eps_preflight_checks_only_selected_lan_and_wan_roles(eps_bundle, monkeypatch):
    monkeypatch.setenv("MEDTECH_EPS_WAN_DOMAIN_TAG", "wan")
    wan = eps_bundle.parent / "1.wan"
    wan.mkdir()
    for filename in ("psk_secret.key", "psk_secret_extra.key"):
        (wan / filename).write_text("test artifact")
    assert (
        eps.launch_environment([("03-remote-teleoperation", ["CdsCloud"])])[
            "RTI_SECURITY_WAN_DOMAIN_DIR"
        ]
        == "1.wan"
    )

    with pytest.raises(ValueError) as exc:
        eps.launch_environment(
            [
                ("02-record-playback", ["RecordingService"]),
                ("03-remote-teleoperation", ["RsActive"]),
            ]
        )
    message = str(exc.value)
    assert "0.or/station/RecordingService/identity.key" in message
    assert "0.or/station/RsActiveLan/identity.key" in message
    assert "1.wan/station/RsActiveWan/identity.key" in message
    assert "ReplayService" not in message and "RsPassive" not in message


def test_eps_cds_selects_managed_profile_without_lan_bundle(monkeypatch, tmp_path):
    domain = tmp_path / "1.wan"
    domain.mkdir()
    for filename in ("psk_secret.key", "psk_secret_extra.key"):
        (domain / filename).write_text("test artifact")
    monkeypatch.setenv("MEDTECH_EPS_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setenv("MEDTECH_EPS_DEPLOYMENT_NAME", "cloud")
    monkeypatch.setenv("MEDTECH_EPS_WAN_DOMAIN_TAG", "wan")
    monkeypatch.delenv("MEDTECH_EPS_DOMAIN_TAG", raising=False)
    spec = (
        [["/opt/rti/bin/rticlouddiscoveryservice", "-cfgName", "CdsConfigCloudSecurity"]],
        tmp_path,
        {},
    )
    monkeypatch.setattr(medtech_cli.launch, "launch_selection", lambda _: [spec])
    monkeypatch.setattr(medtech_cli, "preflight_apps", lambda *_: None)

    def explain(specs, *, explain):
        assert explain
        commands, _, env = specs[0]
        assert commands[0][-1] == "CdsConfigCloudManaged"
        assert env["RTI_SECURITY_WAN_DOMAIN_DIR"] == "1.wan"
        return 0

    monkeypatch.setattr(module_runner, "launch_multi", explain)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "medtech.py",
            "run",
            "03-remote-teleoperation",
            "CdsCloud",
            "--security",
            "--provider",
            "eps",
            "--explain",
        ],
    )
    assert medtech_cli.main() == 0
