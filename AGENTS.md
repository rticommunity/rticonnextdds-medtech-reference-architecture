# Contributor and agent guide

This repository is a teaching/demo architecture, not a clinical implementation.
Start with the root [README](README.md), then the relevant module and
[test guides](tests/README.md).

## Project invariants

- Shared data types are defined in `system/idl/`; edit the IDL, not generated
  bindings. XML owns DDS entities, QoS, services and security configuration.
- Keep command intent distinct from observed feedback. Preserve frames, units
  and finite writer lifespan across direct, routed and replayed streams.
- Keep DDS responsibilities in application adapters, not presentation or
  simulation code. Live DDS tests use real behavior and run sequentially.
- Recording tests use per-test temporary storage. Never clean or overwrite the
  operator's `modules/02-record-playback/or_recording/` directory.
- Contract changes require checking generated bindings, permissions, routing,
  recording/replay, tests and canonical documentation.

## Environment and validation

Use an existing project virtual environment only after checking that its Python
and declared dependencies are compatible. Otherwise create a worktree-local
environment and install the declared developer dependencies. Install the
locked `rti.connext==7.7.0` Python API through uv; do not install a second API
distribution or modify a sibling worktree's environment implicitly.

From the repository root, with the selected Connext environment sourced:

```bash
python -m pip install uv==0.13.8
uv sync --active --locked --no-dev --extra dev --no-install-project
python -m playwright install --with-deps chromium
python resource/python/scripts/check_connext_install.py
python build.py
python -m pytest
python -m pytest --collect-only -q tests/test_config_parsing.py
```

Configure, codegen and build are explicit preparation steps. Pytest and the
Docker test entrypoint verify/run against prepared outputs; they must not
silently rebuild. Run service and other live DDS tests sequentially. A missing
local pytest executable is recoverable; report actual SDK, license, browser or
privilege blockers with the exact attempted command.

Python DDS applications require a valid RTI license at runtime through
`RTI_LICENSE_FILE` or another RTI-supported file location. Keep licenses out of
source, lock files, and image layers.

Check `git config --show-origin --get core.hooksPath` and the existing hook
before configuring pre-commit. Do not overwrite hooks shared by worktrees.
Maintainer checks can be run with `python -m pre_commit run --all-files`;
operators do not need maintainer hooks to run the demo.

For version-qualified DDS APIs, QoS assumptions and test behavior, consult the
[Connext AI expert](https://ai.rti.com/connext-mcp) or an equivalent local
Connext Studio expert when available, then verify against the selected SDK and
real behavior. Never send source, credentials, licenses or runtime samples to
an external tool.
