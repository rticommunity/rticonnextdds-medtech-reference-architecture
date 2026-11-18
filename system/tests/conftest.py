"""Paths for tests of the shared system model and QoS."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "resource" / "python"))
sys.path.insert(0, str(ROOT / "system" / "src"))

from scripts.platform_setup import generated_system_path  # noqa: E402

sys.path.insert(0, str(generated_system_path() / "python"))
