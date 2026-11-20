# Module 02 — Test Suite

Automated tests for the **Record & Playback** module.
Tests verify that RTI Recording Service captures DDS data to a database
and that RTI Replay Service re-publishes recorded samples.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.7.x | `NDDSHOME` must be set |
| Python 3.11+ | With the Connext Python API (`rti.connextdds`) |
| pytest | Install the locked developer dependencies as described in the [project test guide](../../../tests/README.md) |
| Project C++ build complete | From the repository root, run `python medtech.py build` |
| `rtirecordingservice` | Must be present in `$NDDSHOME/bin/` |
| `rtireplayservice` | Must be present in `$NDDSHOME/bin/` |

Tests are automatically skipped if the Recording/Replay Service binaries
are not found.

## Running Tests

From the repository root, after building the project and sourcing the Connext environment:

```bash
# All tests
python -m pytest modules/02-record-playback/tests/ -v

# Only recording tests
python -m pytest modules/02-record-playback/tests/test_recording.py -v

# Only replay tests
python -m pytest modules/02-record-playback/tests/test_replay.py -v
```

## Test Structure

| File | What it tests | Markers |
| --- | --- | --- |
| `test_recording.py` | Recording Service creates a database from live PatientSensor data | `slow` |
| `test_replay.py` | Replay Service re-publishes recorded vitals to a DDS subscriber | `slow` |

## How It Works

1. **Recording test** — Starts PatientSensor (from Module 01) to produce
   `t/patient/vitals` data, launches Recording Service for ~8 seconds, then verifies
   that `or_recording/or_recording_database.dat` exists and has non-trivial size.

2. **Replay test** — First records data (same as above), kills all apps, then
   starts Replay Service and a DDS subscriber subprocess. Verifies that the
   subscriber receives vitals samples from the replayed recording.

Each test copies the service configurations into its own pytest temporary
working directory. Recording and replay output stays there and is removed by
pytest; the normal `modules/02-record-playback/or_recording/` operator data is
never cleaned or used by the tests. The DDS service tests run sequentially.

## Markers

- `@pytest.mark.slow` — All tests in this module are slow (>10s) due to
  the time needed for recording and replay cycles.
