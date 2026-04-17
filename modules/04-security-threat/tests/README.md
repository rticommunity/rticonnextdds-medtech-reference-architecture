# Module 04 — Test Suite

Automated tests for the **Security Threat Demonstration** module.  
Tests verify that DDS Security correctly blocks (or allows) threat
injector and exfiltrator participants depending on the attack mode.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| RTI Connext DDS 7.3.0+ | `NDDSHOME` must be set |
| Python 3.9+ | With the Connext Python API (`rti.connextdds`) |
| pytest | `pip install pytest` |
| Module 01 C++ build complete | Run `python scripts/build.py` in `modules/01-operating-room/` |
| Security artifacts | Run `system_arch/security/setup_security.py` |
| Threat security artifacts | Run `modules/04-security-threat/security/setup_threat_security.py` |

Tests are automatically skipped if security artifacts have not been
generated.

## Running Tests

From the `modules/04-security-threat/` directory:

```bash
# All tests
python -m pytest tests/ -v

# Only injector tests
python -m pytest tests/test_threat_injector.py -v

# Only exfiltrator tests
python -m pytest tests/test_threat_exfiltrator.py -v

# Only unsecure tests (faster)
python -m pytest tests/ -v -k "Unsecure"
```

## Test Structure

| File | What it tests | Markers |
| --- | --- | --- |
| `test_threat_injector.py` | Injector matching against unsecured / secured OR apps | `slow` |
| `test_threat_exfiltrator.py` | Exfiltrator data access against unsecured / secured OR apps | `slow` |

## How It Works

Each test launches Module 01 OR applications (PatientSensor) from the
shared C++ build, then creates a threat DomainParticipant in a subprocess
using the XML-configured participant profiles from `ThreatParticipants.xml`.

- **Injector tests** check `publication_matched_status` to determine whether
  the threat writer matched any OR subscriber.
- **Exfiltrator tests** check `subscription_matched_status` and count received
  samples to determine whether the threat reader can access patient vitals.

Subprocess isolation is required because the threat and OR participant
configurations use separate XML profile namespaces that conflict when
loaded into the same process.

### Test Matrix

| Test | Attack mode | OR mode | Expected result |
| --- | --- | --- | --- |
| `test_unsecure_injection_succeeds` | Unsecure | Unsecure | Matched |
| `test_rogue_ca_injection_blocked` | Rogue CA | Secure | Not matched |
| `test_forged_perms_injection_blocked` | Forged Permissions | Secure | Not matched |
| `test_expired_cert_injection_fails` | Expired Certificate | Secure | Not matched / not created |
| `test_unsecure_exfiltration_succeeds` | Unsecure | Unsecure | Receives vitals |
| `test_unsecure_exfiltrator_vs_secure_or` | Unsecure | Secure | Documented behavior |
| `test_rogue_ca_exfiltrator_blocked` | Rogue CA | Secure | No vitals received |

## Markers

- `@pytest.mark.slow` — All tests in this module are slow (>10s) due to
  DDS discovery and security handshake timeouts.
