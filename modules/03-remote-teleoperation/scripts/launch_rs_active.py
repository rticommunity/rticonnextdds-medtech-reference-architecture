#!/usr/bin/env python3
"""Launch Routing Service (Active) for Module 03."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup
import xml_setup

if __name__ == "__main__":
    security = platform_setup.parse_security_flag()
    env = xml_setup.setup_env(security)
    rs_bin = platform_setup.find_service_binary("rtiroutingservice")

    subprocess.run(
        [
            rs_bin,
            "-cfgFile", "./xml_config/RsConfigActive.xml",
            "-cfgName", "RsConfigActive",
        ],
        env=env,
        check=True,
    )
