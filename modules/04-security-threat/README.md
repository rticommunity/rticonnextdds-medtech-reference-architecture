# Module 04: Security Threat Demonstration

This module demonstrates the security properties of RTI Connext by showing what happens when a malicious application attempts to tamper with surgical arm control commands or steal patient vital signs. Run it alongside [Module 01: Digital Operating Room](../01-operating-room/README.md) to observe attacks succeeding against an unsecured deployment and being blocked by DDS Security in a secured one.

*Note, this module was developed and tested on Debian 11 (Bullseye) and Ubuntu 24.04 running under WSL2 on Windows 11. The instructions below assume a Debian/Ubuntu environment.*

All run commands in this README are launched from the repository root. The project-level `medtech.py run` script is the runtime entrypoint; there is no module-local launcher in this folder.

## Contents

- [Module Description](#module-description)
- [Setup and Installation](#setup-and-installation)
- [Run the Demo](#run-the-demo)
- [Hands-On: Going Further](#hands-on-going-further)
- [Next Steps](#next-steps)

---

## Module Description

Two Python applications serve RTI Demo UI browser frontends and simulate different real-world attack scenarios against the operating room DDS bus. Use `--ui-mode native` to open the same frontend in an embedded desktop webview.

### Threat Injector

The *Threat Injector* application publishes fabricated teleoperation commands on `t/robot/arm/control` and device commands on `t/device/command`, simulating an attacker attempting to disrupt the surgical arm or seize device control through interfaces used by trusted applications. It provides a GUI to select:

- **Attack Mode**. Each of these modes affects whether the DDS Security handshake succeeds or fails. See [Understanding Why Each Attack Is Blocked](#2-understanding-why-each-attack-is-blocked) to understand why the handshake and the attack can fail:
  - Unsecure
  - Rogue CA
  - Forged Permissions
  - Expired Certificate
- **Attack Type**:
  - Teleop Inject. This publishes complete base-frame TCP velocity samples at a configurable frequency, using the same finite-lifespan control profile as the demo controller.
  - Command Inject PAUSE (one-shot)
  - Command Inject SHUTDOWN (one-shot)
- **Frequency Slider**
  - The slider controls how many times per second the Teleop Inject attack writes samples.
  - This is only enabled when Teleop Inject is selected and an attack is not already running.

Attack status is derived from `publication_matched_status` — the app checks whether its DataWriters have matched any remote subscribers. If a subscriber matches (unsecured OR is running), the status badge shows **ATTACKING** (green) and log entries appear as `[OK]`. If no subscriber matches (secured OR blocks the handshake), the status badge shows **NO ACCESS** (orange) and log entries appear as `[WARN]`.

The local model preview is explicitly labeled as a command simulation, **not
observed arm feedback or proof of actuation**. The activity stream records
participant, match, and write outcomes. A matching reader only establishes an
open data path; consult the live Arm's observed telemetry to confirm execution.
No new tool/status attack capability is added. Low injection rates can leave
gaps longer than command lifespan, during which the Arm holds its current pose.
Preview initialization, simulation, and rendering-state failures disable only
the optional preview, with an explicit warning. DDS intent generation and
publication continue independently; unavailable preview values are not
substituted with simulated success or observed feedback.

This scenario intentionally introduces a competing command writer. Outside
this threat demonstration, use one OR, one instance per application role, and
one intended live-controller **or** replay source. DDS matching does not
arbitrate command ownership.

### Threat Exfiltrator

The *Threat Exfiltrator* application subscribes to the `t/patient/vitals` topic, displaying patient vital signs as if harvesting them for unauthorised use. Attack status is derived from `subscription_matched_status` — when the exfiltrator's DataReader matches a remote publisher, the interface shows **ACCESS GRANTED** and live heart rate, SpO₂, EtCO₂, and NiBP values stream in. When no match occurs (secured OR), the visualizations show unavailable values and the status shows **NO ACCESS**. A separate data-state indicator distinguishes waiting for vitals, live data, and a quiet/stale stream. Its activity stream records DDS and security events.

### Status States

Both applications use the following status states:

| Status | Color | Meaning |
| --- | --- | --- |
| **IDLE** | ⚪ **Grey** | No attack mode selected |
| **ACCESS GRANTED** | 🟢 **Green** | DDS matched — data path is open |
| **ATTACKING** | 🟢 **Green** | Actively writing samples that reach a subscriber (injector only) |
| **NO ACCESS** | 🟠 **Orange** | No DDS match — security or configuration is blocking the connection |
| **ATTACK FAILED** | 🔴 **Red** | Participant creation itself failed (e.g. expired certificate rejected at startup) |

---

## Setup and Installation

Complete the shared setup in the root [Quick Start](../../README.md#quick-start) section. This module reuses the operating room applications from Module 01, so make sure that workflow is already working before you begin.

Module-specific setup:

Prepare the [local security bundle](../../system/security/README.md) first so the
generated keys and trust stores are available on the machines that run this
module. Select `--provider local` if another provider is saved.

Generate the module-specific threat artifacts from the repository root:

```bash
# From the repository root
python3 modules/04-security-threat/security/setup_threat_security.py
```

*Note, the **Forged Permissions** and **Expired Certificate** attack modes require the trusted system CA private keys (e.g. `system/security/ca/TrustedIdentityCa/private/TrustedIdentityCa.key`). These keys are generated when you complete the shared security setup in the root README and are used only for laboratory demonstration of how certificate chains can be abused. Keep them secure in any real deployment.*

Ensure the RTI Security Plugins are installed on every machine that will run a secured participant.

---

## Run the Demo

> Important: Run the commands below from the repository root. `medtech.py run` lives at the project root and is the single runtime entrypoint for this project.
>
> Tip: the predefined `security-threat`, `threat-inject`, and `threat-exfiltrate` scenarios bundle the operating room apps with the threat application(s) in a single command (e.g. `python medtech.py run --scenario threat-inject`). The step-by-step flow below runs them in separate terminals so you can switch the OR between unsecured and secured modes independently. Run `python medtech.py run --list-scenarios` to see all scenarios.

### 1. Run Operating Room Applications

Open a terminal and launch Module 01 from the repository root in either unsecured or secured mode:

```bash
# From the repository root
# Unsecured (attacks will SUCCEED):
python medtech.py run 01-operating-room

# Secured (attacks will be BLOCKED):
python medtech.py run 01-operating-room -s
```

### 2. Run a Threat Application

Open a second terminal and launch the desired threat application:

```bash
# From the repository root
# Launch the Threat Injector:
python medtech.py run 04-security-threat ThreatInjector

# OR launch the Threat Exfiltrator:
python medtech.py run 04-security-threat ThreatExfiltrator
```

### 3. Observe the Application Behavior

1. Select an **Attack Mode** (this creates the DDS participant and enables the attack type and launch controls).
2. Select an **Attack Type** (defaults to Motor Inject).
3. Click **LAUNCH ATTACK**.

The activity stream and security status update in real time. Each graphical app
prints the local URL to open; the browser is the default presentation mode.

| Scenario | OR mode | Attack mode | Threat app | OR app |
| --- | --- | --- | --- | --- |
| Teleop inject | Unsecured | Unsecure | Status: **ATTACKING**; `[OK]` log entries; arm viz moves | *Arm* browser view moves erratically |
| Teleop inject | Secured | Rogue CA | Status: **NO ACCESS**; `[WARN]` log entries; arm viz moves locally | *Arm* unaffected |
| Teleop inject | Secured | Forged Perms | Status: **NO ACCESS**; `[WARN]` log entries; arm viz moves locally | *Arm* unaffected |
| Teleop inject | Secured | Expired Cert | Status: **ATTACK FAILED**; participant creation blocked | *Arm* unaffected |
| Vitals exfiltrate | Unsecured | Unsecure | Status: **ACCESS GRANTED**; vitals panels populate | *Patient Monitor* continues normally |
| Vitals exfiltrate | Secured | Rogue CA | Status: **NO ACCESS**; vitals panels show `---` | *Patient Monitor* continues normally |
| Vitals exfiltrate | Secured | Expired Cert | Status: **ATTACK FAILED**; participant creation blocked | *Patient Monitor* continues normally |

> [!NOTE]
> **Observe:** In unsecured mode, select **Teleop Inject → LAUNCH ATTACK**: the *Arm* browser view moves erratically without a legitimate operator. Restart the OR in secured mode (`-s`) and repeat: the arm is unaffected and the injector reports **NO ACCESS**.

> [!NOTE]
> **Observe:** Rogue CA and Forged Permissions both result in **NO ACCESS**: no publication match and no data flowing.

The DDS Security handshake fails at different stages for those two attack modes.

### 4. Kill the Applications

Press `Ctrl-C` in each terminal to terminate the running applications.

---

## Hands-On: Going Further

### 1. Comparing Unsecured vs. Secured Behavior

While the injector is actively attacking in **Unsecure** mode against the unsecured OR (status: **ATTACKING**, green), restart the OR applications in secured mode without stopping the threat app:

```bash
# From the repository root
# Press Ctrl-C to stop the running OR apps, then relaunch with security:
python medtech.py run 01-operating-room -s
```

Watch the threat app's Activity Log: when the secured OR comes up, the injector's `publication_matched_status` drops to zero and the status badge transitions from **ATTACKING** to **NO ACCESS**. The `[OK]` log entries become `[WARN]`, indicating writes are still happening locally but no subscriber is receiving them.

### 2. Understanding Why Each Attack Is Blocked

Each attack mode corresponds to a different stage of the DDS Security handshake. Even if an attacker passes one layer, subsequent layers still block the attack:

> **Note:** All three attack modes share a common `InsiderBase` profile (in [ThreatQos.xml](xml_config/ThreatQos.xml)) that supplies the genuine `OperationalDomain.psk` seed via `dds.sec.crypto.rtps_psk_secret_passphrase`. This deliberately models an *insider* who has already obtained the domain pre-shared key, so the attacker clears the outer `rtps_psk_protection_kind=ENCRYPT` layer. The block therefore happens at the authentication, access-control, or certificate-validation stage below — demonstrating that the domain PSK alone is not sufficient to join the secured OR.

| Mode | What happens | Why |
| --- | --- | --- |
| **Rogue CA** | Participant is created but never matches | The identity certificate is signed by an untrusted CA root. The OR participants do not list the rogue CA in their `identity_ca` trust store, so the authentication handshake fails. |
| **Forged Permissions** | Participant is created but never matches | Authentication succeeds (identity signed by trusted CA), but the permissions document is signed by the rogue CA. Since the OR's `permissions_ca` is the trusted CA, the signature mismatch causes access control validation to fail. |
| **Expired Certificate** | Participant creation fails immediately | The identity certificate was signed by the trusted CA but its `notAfter` field is in the past. The DDS Security authentication plugin validates certificate expiration during identity validation — for the local participant, this occurs during DomainParticipant creation, causing it to fail immediately. The status badge shows **ATTACK FAILED** (red). |

Beyond authentication and permissions, the system also enforces **cryptographic protection at multiple levels**:

- **Domain-level protection from outsiders:** `rtps_psk_protection_kind=ENCRYPT` protects pre-authentication traffic, preventing passive eavesdropping before the handshake completes.
- **Domain-level protection from insiders:** `rtps_protection_kind=ENCRYPT_WITH_ORIGIN_AUTHENTICATION` ensures all RTPS traffic is encrypted with per-writer keys and origin-authenticated — even an authenticated insider cannot forge another participant's messages.
- **Topic-level protection from insiders:** `t/patient/vitals` and `t/robot/arm/control` use `metadata_protection_kind=ENCRYPT`, meaning their submessage metadata is encrypted with keys shared only among authorized endpoints — a compromised participant without topic-level permissions cannot decrypt these topics.

For a deeper dive into the DDS Security handshake, refer to the [RTI Security Plugins User's Manual](https://community.rti.com/static/documentation/connext-dds/7.7.0/doc/manuals/connext_dds_secure/users_manual/p2_core/authentication.html#handshake).

---

## Next Steps

**Next → [Inspect the DDS Security design](../../system/DDS_DESIGN_GUIDE.md#security).**
Follow the [security guide](../../system/security/README.md) to find governance,
participant grants, and the credentials used at runtime.
