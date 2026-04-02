#!/usr/bin/env python3
"""Launch Cloud Discovery Service for Module 03."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / ".." / ".." / ".." / "system_arch" / "scripts"))
import platform_setup

if __name__ == "__main__":
    security = platform_setup.parse_security_flag()
    cds_bin = platform_setup.find_service_binary("rticlouddiscoveryservice")

    if security:
        print("Launching CDS with Security...")
        cfg_name = "CdsConfigCloudSecurity"
    else:
        print("Launching CDS without Security...")
        cfg_name = "CdsConfigCloud"

    subprocess.run(
        [
            cds_bin,
            "-cfgFile", "./xml_config/CdsConfigCloud.xml",
            "-cfgName", cfg_name,
        ],
        check=True,
    )
