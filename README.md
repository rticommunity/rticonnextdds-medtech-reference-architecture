# RTI MedTech Reference Architecture

## Overview

See how a simulated operating room shares patient vitals, device status, and
robot motion commands using RTI Connext DDS. This source project demonstrates
DDS design choices; it is not production software or a clinical system.

## Prerequisites

- Install [Connext DDS 7.7.0](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/installation_guide/installing.html)
  with the target libraries for your platform and get a valid `rti_license.dat`
  from [RTI Evaluation](https://evaluation.rti.com/) or the [Customer Portal](https://support.rti.com/).
- Have Git, Python 3.11–3.14 with `venv`, CMake 3.18+, and a C++ compiler.
  If you’re missing any, use the install commands under your platform below.

## Quick start

Replace the example SDK and license paths. First build requires internet access.
For browser mode, skip native setup, omit `--ui-mode native`, and open the printed URLs.

### Install missing build tools

Skip this section if you already have the prerequisites.

<!-- platform-tabs:start -->
#### Linux

```bash
sudo apt update
sudo apt install build-essential cmake git pkg-config python3 python3-venv
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev
```

Debian/Ubuntu; use a Python 3.11–3.14 interpreter.

#### macOS

```bash
xcode-select --install
brew install cmake git pkg-config
```

[Install Python 3.11–3.14](https://www.python.org/downloads/macos/) and
[Homebrew](https://brew.sh/) if needed.

#### Windows

```bat
winget install -e --id Git.Git
winget install -e --id Kitware.CMake
```

[Install Python 3.11–3.14](https://www.python.org/downloads/windows/) and
[Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio)
with the **Desktop development with C++** workload and a toolset matching your
Connext target.
<!-- platform-tabs:end -->

### Configure and launch

<!-- platform-tabs:start -->
#### Linux

```bash
source "/path/to/connext/resource/scripts/rtisetenv_<arch>.bash"
export RTI_LICENSE_FILE="/path/to/rti_license.dat"
git clone https://github.com/rticommunity/rticonnextdds-medtech-reference-architecture.git
cd rticonnextdds-medtech-reference-architecture
python3 -m venv .venv
source .venv/bin/activate
```

For distro Python 3.13 or 3.14, complete the
[GTK bindings setup](docs/SETUP.md#linux-system-gtk-bindings) before launching.
For other Python installations, ensure GTK bindings are available or use browser mode.

#### macOS

```bash
source "/path/to/connext/resource/scripts/rtisetenv_<arch>.bash"
export RTI_LICENSE_FILE="/path/to/rti_license.dat"
git clone https://github.com/rticommunity/rticonnextdds-medtech-reference-architecture.git
cd rticonnextdds-medtech-reference-architecture
python3 -m venv .venv
source .venv/bin/activate
```

Use a supported `python3` version and check the
[native-webview requirements](docs/SETUP.md#native-windows) for your macOS release.

#### Windows

Use a **Developer Command Prompt for Visual Studio**, not PowerShell.

```bat
call "C:\path\to\connext\resource\scripts\rtisetenv_<arch>.bat"
set "RTI_LICENSE_FILE=C:\path\to\rti_license.dat"
git clone https://github.com/rticommunity/rticonnextdds-medtech-reference-architecture.git
cd rticonnextdds-medtech-reference-architecture
py -m venv .venv
call .venv\Scripts\activate.bat
```

Use a supported `py` version (for example, `py -3.14`) and check the
[native-webview requirements](docs/SETUP.md#native-windows) for Windows.
<!-- platform-tabs:end -->

### Try it

```bash
python medtech.py up --scenario or-all --ui-mode native
```

When Orchestrator and Patient Monitor are open, select **Patient Sensor** in
Orchestrator and click **PAUSE**. Watch the vitals stop updating, then click
**START** to resume.

**Walkthrough → [Try the arm controller in Module 01](modules/01-operating-room/README.md#try-the-arm-controller).**
Leave the apps and vitals running to follow along. Press Ctrl-C when you’re done.
For more setup options, see the [platform setup guide](docs/SETUP.md).

## Modules

| Start here | What it demonstrates |
| --- | --- |
| [01 · Digital operating room](modules/01-operating-room/) | Typed data flows, device presence, and motion commands with separate feedback. |
| [02 · Record and replay](modules/02-record-playback/) | Capture a DDS session and replay selected data into the same applications. |
| [03 · Remote teleoperation](modules/03-remote-teleoperation/) | Route selected topics between separate networks using Real-Time WAN Transport. |
| [04 · DDS Security demonstration](modules/04-security-threat/) | Observe how different trust and authorization states affect the same system. |

## Architecture

The shared contract lives under `system/`, separate from the applications and
their browser and simulation code:

| Location | Defines |
| --- | --- |
| `idl/` | The types and keys used on the wire. |
| `model/` | Domains, topics, participants, readers, and writers. |
| `qos/` | Delivery, history, and timing policies. |
| `security/` | Domain protections and what each participant role may do. |

Follow the [DDS contract](system/README.md#dds-contract) to trace a data flow
from its type to the applications that exchange it. For focused C++, Python,
XML, and CMake examples, see the
[reusable DDS guidance](system/README.md#reusable-dds-guidance).

## Security

In secure mode, DDS Security authenticates participants and enforces which
roles may publish or subscribe to each topic. For example, Patient Monitor can
receive vitals but cannot issue arm motion commands. Governance sets which
DDS traffic is encrypted for confidentiality and cryptographically protected
against tampering.

| Provider | Where to use it |
| --- | --- |
| [Local OpenSSL](system/security/README.md#generating-security-artifacts) (default) | Modules 01–04; self-signed credentials for a local demo. |
| [RTI Edge Provisioning Service](docs/EPS.md) (opt-in) | Modules 01–03; agent-managed credentials. Module 01 is qualified end to end; Modules 02–03 still need end-to-end EPS qualification. |

See the [DDS Security design](system/DDS_DESIGN_GUIDE.md#security) for governance and
role permissions. The demo does not establish clinical security or compliance.

## References

- [RTI MedTech case and code](https://www.rti.com/developers/case-code/medtech-reference-architecture)
- [Connext product documentation](https://community.rti.com/documentation)
- [Contributing and documentation preview](docs/CONTRIBUTING.md)
