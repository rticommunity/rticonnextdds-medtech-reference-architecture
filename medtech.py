# PYTHON_ARGCOMPLETE_OK
# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

"""Project CLI bootstrap; works before project dependencies are installed."""

import sys
from pathlib import Path

if not (3, 11) <= sys.version_info[:2] < (3, 15):
    raise SystemExit("MedTech requires Python 3.11–3.14.")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.medtech.medtech_cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
