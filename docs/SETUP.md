# Platform setup and build options

For the shortest path, use the [Quick start](../README.md#quick-start). This page explains the SDK, platform packages, and optional setup steps.

## Prerequisites

- **RTI Connext DDS SDK 7.7.0** installed and `NDDSHOME` set. The SDK supplies
  the C++ libraries, IDL/code-generation tools, services, and add-ons; the
  Python API is installed separately from PyPI by the project lock.
  See the [Installation Guide](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/installation_guide/installing.html).
  Python DDS applications using the locked PyPI API need a valid RTI license
  at runtime; see [License Management](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_professional/installation_guide/license_management.html).

  > If `NDDSHOME` is not already in your environment, source the platform setup script from your Connext installation: `source <connext_dir>/resource/scripts/rtisetenv_<arch>.bash` (Linux/macOS) or `rtisetenv_<arch>.bat` (Windows). This script sets `NDDSHOME`, `CONNEXTDDS_ARCH`, and related library paths required to build and run the demo.
- **CMake** ≥ 3.18 and a C++ compiler toolchain.
- **Python** ≥ 3.11.
- A valid `rti_license.dat` from the [evaluation site](https://evaluation.rti.com/)
  or [customer portal](https://support.rti.com/). Keep it outside the checkout
  and set `RTI_LICENSE_FILE` to its absolute path.

See the [platform install commands](../README.md#quick-start) for the base
build tools. On Debian/Ubuntu, `python3-venv` is separate from `python3`.

## Native windows

Browser mode is the default and does not require a desktop GUI toolkit. To
build optional C++ native-webview support on Linux, also install GTK 3 and
WebKitGTK 4.1 development packages:

```bash
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev
```

Check the [native-webview platform requirements](https://wcoleman-rti.github.io/rti-demo-ui/native-webview.html)
for your OS. On Debian/Ubuntu with Python 3.13 or newer, follow the
[system GTK bindings setup](#linux-system-gtk-bindings) from the cloned
repository **before** running `up` in native mode.

## Explicit environment setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install uv==0.13.8
uv sync --active --locked --no-dev --extra user
python tools/medtech/check_connext_install.py
```

[`pyproject.toml`](../pyproject.toml) defines capability and persona extras;
[`uv.lock`](../uv.lock) records resolved dependencies across platforms. The
`user` persona includes the Arm simulation and gamepad capabilities. Use
`--extra arm` instead for the Arm without the gamepad, or omit the extra for
the base dependencies only. The lock pins the Python distribution
`rti.connext==7.7.0`, imported in code as `rti.connextdds`; do not install a
second API distribution manually. The exact locked sync installs and keeps
that API, but can remove separately installed physical-device packages.
For Kortex or Falcon setup, preserve and verify the selected environment as
described in the [physical-device guide](../modules/01-operating-room/ARM_AND_CONTROLLER.md#physical-device-development).
The compatibility preflight checks the Python distribution,
code generator, and installed Core and Security inventory and library build
IDs against the same patch (currently 7.7.0.0). It checks the selected
installation, not which libraries the runtime loader actually selects; ensure
the library search paths also point to that installation. The lock does not
install the Connext SDK, system libraries, compiler, or all build tools.

Obtain a valid `rti_license.dat` from the [RTI Evaluation site](https://evaluation.rti.com/)
or, for licensed customers, the [RTI Customer Portal](https://support.rti.com/).
Keep the file outside the repository and configure its full path through
`RTI_LICENSE_FILE`; do not add it to source control or bake it into an image:

```bash
export RTI_LICENSE_FILE=/secure/path/to/rti_license.dat
python tools/medtech/smoke_connext_runtime.py
```

The separate runtime smoke creates and closes a DDS participant, so run it
only where a valid license is available. It is not part of license-free tests.
The PyPI package requires a license when an application creates a participant.
RTI also supports a license file in the application working directory or a
participant QoS license setting; use the environment variable for local,
container, and CI secret-based setups.

Optional Python native-webview mode can be installed separately with
`uv sync --active --locked --no-dev --extra user --extra native`.
Browser mode does not need this companion package. The embedded native window hosts the same web frontend;
review the SDK's [native-webview support matrix and platform prerequisites](https://wcoleman-rti.github.io/rti-demo-ui/native-webview.html)
before enabling it on a target platform.

The simulated Arm uses MuJoCo and Mink, installed through the `arm` capability.
It runs headlessly and retains the project's existing renderer; no ROS, GPU,
or separate simulator service is required. MuJoCo is pinned to 3.10.0 to retain
native wheels for Intel macOS as well as Apple Silicon, Linux, and Windows.
See the [Arm model and simulation notes](../modules/01-operating-room/ARM_AND_CONTROLLER.md#arm-model-command-validity-and-observed-feedback).

Third-party dependencies retain their own licenses; the project's
Connext-specific license applies to project-authored code, not those packages.
[MuJoCo](https://github.com/google-deepmind/mujoco/blob/main/LICENSE) and
[Mink](https://github.com/kevinzakka/mink/blob/main/LICENSE) use Apache-2.0,
[qpsolvers](https://github.com/qpsolvers/qpsolvers/blob/main/LICENSE) uses
LGPL-3.0, and [DAQP](https://github.com/darnstrom/daqp/blob/master/LICENSE)
uses MIT. These packages are installed from upstream, not vendored here.
Keep their notices/licenses and ability to replace the library intact if
redistributing an environment, container, or packaged application.

### Linux system GTK bindings

On Debian/Ubuntu with Python 3.13 or newer, Python native mode also uses the
distro-provided GTK bindings; pip intentionally does not install PyGObject for
these Python versions. Install the GTK/WebKit typelibs and create the virtual
environment with system packages visible:

```bash
sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-gi
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install uv==0.13.8
uv sync --active --locked --no-dev --extra user --extra native
python tools/medtech/check_connext_install.py
```

Run the `apt` command from any directory. Run the remaining commands from
the cloned repository root. If you are using `up`, stop after creating `.venv`;
`up` installs the locked native dependencies into it. Otherwise, follow the
rest of the block instead of the standard isolated venv setup above.
For an existing isolated environment,
rerun `python3 -m venv --system-site-packages .venv` to expose the system `gi`
binding. Exact uv synchronization manages the virtual environment and leaves
distro packages visible through `--system-site-packages`. The interpreter used
for the venv must match the distro's `python3-gi` build. Verify it with
`python -c "import gi; gi.require_version('WebKit2', '4.1'); from gi.repository import WebKit2"`;
system packages may not support a separately installed Python interpreter.

## Build and launch options

Build all modules:

```bash
python medtech.py build
```

To build only the modules you intend to run:

```bash
python medtech.py build -- -- --target module-01   # all C++ targets in Module 01
python medtech.py build -- -- --target ArmController  # only the ArmController target
```

The first `--` ends CLI options; the second sends the remaining arguments to
`cmake --build` instead of CMake configure.

The compiled binaries are placed under `build/<CONNEXTDDS_ARCH>/`.
The shared [system definition](../system/README.md) is IDL-first. The same build
generates C++, joined Python, and XML under
`build/<CONNEXTDDS_ARCH>/system/generated/`; application source directories do not
own shared generated bindings. The launcher exposes the generated Python path
while preserving inherited `PYTHONPATH`. Build before launching Python-only
variants too. For direct runs, add the absolute generated `python/` directory to
`PYTHONPATH` and use the module's normal DDS environment.

The C++ core and optional native companion are consumed from the RTI Demo UI
repository root in one CMake build. The Python core and native runner are
installed from the same pinned SDK revision using its root package and
`native/python` subpackage, respectively. To enable native-webview support for
the C++ graphical apps, configure with:

```bash
python medtech.py build -- -DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON
```

Launch browser mode by default, or select the embedded desktop webview after
installing/building the matching native companion:

```bash
python medtech.py run 01-operating-room
python medtech.py run 01-operating-room --ui-mode native
```

Graphical apps label each printed local URL with the application name so the
browser or native-window endpoint can be identified when several apps start
together. Native mode opens the windows automatically; those URLs are diagnostic
endpoints, not instructions to open a separate browser. Browser mode remains the
default and requires opening the printed URLs manually. Both modes use the same
responsive layouts: controls and panels reflow in narrow windows, and short
windows scroll vertically instead of clipping controls.
