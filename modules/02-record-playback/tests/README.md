# Module 02 — Test Suite

Automated tests for the **Record & Playback** module.  
Tests verify that RTI Recording Service captures DDS data to a database
and that RTI Replay Service re-publishes recorded samples.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.3.0+ | `NDDSHOME` must be set |
| Python 3.9+ | With the Connext Python API (`rti.connextdds`) |
| pytest | `pip install pytest` |
| Module 01 C++ build complete | Run `python scripts/build.py` in `modules/01-operating-room/` |
| `rtirecordingservice` | Must be present in `$NDDSHOME/bin/` |
| `rtireplayservice` | Must be present in `$NDDSHOME/bin/` |

Tests are automatically skipped if the Recording/Replay Service binaries
are not found.

## Running Tests

From the `modules/02-record-playback/` directory:

```bash
# All tests
python -m pytest tests/ -v

# Only recording tests
python -m pytest tests/test_recording.py -v

# Only replay tests
python -m pytest tests/test_replay.py -v
```

## Test Structure

| File | What it tests | Markers |
| --- | --- | --- |
| `test_recording.py` | Recording Service creates a database from live PatientSensor data | `slow` |
| `test_replay.py` | Replay Service re-publishes recorded vitals to a DDS subscriber | `slow` |

## How It Works

1. **Recording test** — Starts PatientSensor (from Module 01) to produce
   `t/Vitals` data, launches Recording Service for ~8 seconds, then verifies
   that `or_recording/or_recording_database.dat` exists and has non-trivial size.

2. **Replay test** — First records data (same as above), kills all apps, then
   starts Replay Service and a DDS subscriber subprocess. Verifies that the
   subscriber receives vitals samples from the replayed recording.

Both tests use a `clean_recording_dir` fixture that removes any previous
recording output before each run.

## Markers

- `@pytest.mark.slow` — All tests in this module are slow (>10s) due to
  the time needed for recording and replay cycles.
