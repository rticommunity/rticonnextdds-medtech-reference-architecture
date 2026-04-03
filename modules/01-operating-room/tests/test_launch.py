"""Launch / smoke tests for Module 01 applications.

Verifies that each application starts without crashing.
GUI applications are marked so they can be skipped on headless systems.
"""

import time

import pytest


STARTUP_WAIT = 3  # seconds to let a process initialise


class TestPatientSensor:
    """PatientSensor is a headless C++ app — no display needed."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_cpp("PatientSensor")
        time.sleep(STARTUP_WAIT)
        assert proc.poll() is None, (
            f"PatientSensor exited early with code {proc.returncode}"
        )

    def test_prints_launch_message(self, proc_manager):
        proc = proc_manager.start_cpp("PatientSensor")
        # Read stdout with a timeout
        time.sleep(STARTUP_WAIT)
        # Read whatever is available, non-blocking
        out = proc.stdout.read1(4096).decode(errors="replace") if hasattr(proc.stdout, "read1") else b""
        # Fallback: terminate and capture
        if not out:
            proc.terminate()
            stdout, _ = proc.communicate(timeout=5)
            out = stdout.decode(errors="replace")
        assert "Launching Patient Sensor" in out


@pytest.mark.gui
class TestOrchestrator:
    """Orchestrator is a C++ GTK application."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_cpp("Orchestrator")
        time.sleep(STARTUP_WAIT)
        assert proc.poll() is None, (
            f"Orchestrator exited early with code {proc.returncode}"
        )


@pytest.mark.gui
class TestArmController:
    """ArmController is a C++ GTK application."""

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_cpp("ArmController")
        time.sleep(STARTUP_WAIT)
        assert proc.poll() is None, (
            f"ArmController exited early with code {proc.returncode}"
        )


@pytest.mark.gui
class TestPatientMonitor:
    """PatientMonitor is a Python/Qt application — use offscreen platform."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_python("PatientMonitor.py", extra_env=self.QT_ENV)
        time.sleep(STARTUP_WAIT)
        assert proc.poll() is None, (
            f"PatientMonitor exited early with code {proc.returncode}"
        )


@pytest.mark.gui
class TestArm:
    """Arm is a Python/Qt application — use offscreen platform."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}

    def test_starts_and_stays_alive(self, proc_manager):
        proc = proc_manager.start_python("Arm.py", extra_env=self.QT_ENV)
        time.sleep(STARTUP_WAIT)
        assert proc.poll() is None, (
            f"Arm exited early with code {proc.returncode}"
        )


@pytest.mark.gui
class TestAllApps:
    """Launch all five applications simultaneously."""

    QT_ENV = {"QT_QPA_PLATFORM": "offscreen"}

    def test_all_apps_launch_together(self, proc_manager):
        procs = {
            "PatientSensor": proc_manager.start_cpp("PatientSensor"),
            "Orchestrator": proc_manager.start_cpp("Orchestrator"),
            "ArmController": proc_manager.start_cpp("ArmController"),
            "PatientMonitor": proc_manager.start_python(
                "PatientMonitor.py", extra_env=self.QT_ENV
            ),
            "Arm": proc_manager.start_python("Arm.py", extra_env=self.QT_ENV),
        }

        time.sleep(5)

        for name, proc in procs.items():
            assert proc.poll() is None, (
                f"{name} crashed on startup (exit code {proc.returncode})"
            )
