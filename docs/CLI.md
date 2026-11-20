# MedTech command-line guide

Run commands from the repository root with Python 3.11–3.14 and the
[Connext environment configured](SETUP.md#prerequisites). Examples use `python`;
use the supported interpreter from [Quick Start](../README.md#quick-start)
(such as `python3` on Linux/macOS or `py` on Windows) if that is how you launch it.
Start with:

```bash
python medtech.py up --scenario or-all
```

Open the browser URLs printed in the terminal. Press Ctrl-C in that terminal
to stop the apps. For a live walkthrough, see the [operator run card](OPERATOR.md).

## Choose a command

| Command | Use it to |
| --- | --- |
| `python medtech.py setup --extra arm` | Install the locked workspace environment, including arm simulation dependencies. |
| `python medtech.py build` | Configure CMake, generate types from IDL, and build the C++ apps. |
| `python medtech.py run --scenario or-all` | Launch from prepared outputs without installing or building. Use this at a prepared/offline demo station. |
| `python medtech.py up --scenario or-all` | Select dependencies, set up, build, and launch in order. |
| `python medtech.py run --scenario or-all --explain` | Check prepared outputs and print commands without starting apps. |
| `python medtech.py security plan` | Print credential preparation steps; never enroll or issue credentials. |

Use `python medtech.py run --list-scenarios` to discover available scenarios.
For a narrower launch, pass a module and one or more app roles:

```bash
python medtech.py run 01-operating-room Orchestrator PatientMonitor
```

The default arm controller is simulated. Add `--variant ArmController=xbox`
to `up`, or install `--extra gamepad` before using that variant with `run`.
Pass CMake options to `build` after `--`, for example
`python medtech.py build -- -DCMAKE_BUILD_TYPE=Release`.

## Enable security

The default provider is [local OpenSSL](../system/security/README.md).
Prepare its bundle explicitly, then add `--security` to launch.
For Modules 01–03, you can instead select [Edge Provisioning Service](EPS.md):

```bash
python medtech.py security plan --provider eps
python medtech.py run --scenario or-all --security --provider eps --explain
```

The preflight reports missing artifacts; it does not start the agent, contact
the cloud, or verify live DDS communication. Use `security plan --save` to
remember a provider name, or pass `--provider` on a secure launch to override it.
