# RTI Edge Provisioning Service

EPS is an opt-in provider for Modules 01–03. The local OpenSSL provider remains
the default. The Module 01 workflow was qualified on Linux with Connext 7.7.0
and `rticloud` 0.5.2. The service modules require separate runtime qualification.
Use an active test EPS instance and an authorized Cloud operator.
See [RTI's Edge Provisioning tutorial](https://community.rti.com/static/documentation/developers/learn/connext-cloud-edge-provisioning.html)
for CLI installation and sign-in.

## Maintainer: configure the service once

From the repository root, sign in with `rticloud login` in the service's region.
Use a test service. The example uses a tagged Full Security domain template to
avoid replacing the default domain `0` template. The following shell commands use
Bash; set `SERVICE` to your service name.

```bash
POLICY=system/security/domain_scope/OperationalDomain
rticloud edge-provisioning governance-template create \
  --service "$SERVICE" --name medtech-or-governance \
  --governance-file "$POLICY/governance/OperationalDomain/OperationalDomain.xml"
rticloud edge-provisioning domain-template create \
  --service "$SERVICE" --domain-id 0 --domain-tag medtech-or --security-mode full \
  --governance-template medtech-or-governance

for role in Arm ArmController Orchestrator PatientSensor PatientMonitor SecureLogReader; do
  rticloud edge-provisioning permissions-template create \
    --service "$SERVICE" --name "medtech-or-$role" \
    --permissions-file "$POLICY/permissions/$role/$role.xml"
  rticloud edge-provisioning participant-template create \
    --service "$SERVICE" --name "$role" --permissions-ref "medtech-or-$role"
done
```

Verify the bindings under **Templates**. EPS signs the distributed files and
binds grants to the enrolled identity, domain/tag, and validity period. Keep the
committed rules as the policy source. Do not substitute `permissions-allow-all`.

## Edge operator: enroll the deployment

Set `SERVICE_ID` and `DOMAIN_TEMPLATE_ID` to the values reported by the test
service (`domain-template list` shows the template ID). Each host should use a
distinct deployment name. Keep the following credentials outside source control.

From the repository root, set these variables in the shell that will launch MedTech:

```bash
umask 077
export MEDTECH_EPS_ARTIFACTS_DIR="$PWD/.medtech/eps/artifacts"
export MEDTECH_EPS_DEPLOYMENT_NAME=or-station-01
export MEDTECH_EPS_DOMAIN_TAG=medtech-or
mkdir -p .medtech/eps
```

In an agent terminal with the same variables, sign in with `rticloud login`,
change into `.medtech/eps`, and start the agent. Leave it running.

```bash
rticloud edge-sync agent --service "$SERVICE_ID" \
  --domain-tpl-id "$DOMAIN_TEMPLATE_ID" --participant-tpl-id PatientSensor \
  --deployment-name "$MEDTECH_EPS_DEPLOYMENT_NAME" \
  --connext-dir "$MEDTECH_EPS_ARTIFACTS_DIR"
```

In another terminal using the same agent working directory and variables, queue
the remaining roles:

```bash
for role in Arm ArmController Orchestrator PatientMonitor SecureLogReader; do
  rticloud edge-sync agent enroll --service "$SERVICE_ID" \
    --domain-tpl-id "$DOMAIN_TEMPLATE_ID" --participant-tpl-id "$role" \
    --deployment-name "$MEDTECH_EPS_DEPLOYMENT_NAME" \
    --connext-dir "$MEDTECH_EPS_ARTIFACTS_DIR"
done
```

From the repository root, with the three `MEDTECH_EPS_*` variables set:

```bash
python medtech.py up --scenario or-all --security --provider eps
```

Use `run` instead of `up` when already built, or `run --explain` for a no-spawn
check. The launcher checks readable, nonempty files before setup/build or launch.
It does not verify signatures, certificate expiry, or policy compatibility;
Connext performs authentication and access control at runtime.
It does not run `rticloud`, change files, or fall back to local credentials.
Open the printed URLs and follow the [operator run card](OPERATOR.md).

Stop the demo and the agent separately with Ctrl-C in their terminals. To resume,
restart the agent in the same directory; use the existing enrollment. Automatic
renewal and revocation behavior has not been qualified for this demo.

## Module 02: record and replay

Use the same tagged LAN domain template as Module 01. Import the committed
`RecordingService` and `ReplayService` grants from `OperationalDomain` by adding
the two names to the maintainer's role loop. Enroll the service role you will run
in the same LAN template as the operating-room apps. Recording and replay have
separate identities and permissions; do not share a more permissive identity.

```bash
python medtech.py run --scenario record --security --provider eps
# Stop recording before starting replay.
python medtech.py run --scenario replay --security --provider eps
```

See the [Module 02 guide](../modules/02-record-playback/README.md) for recording
and replay controls. The launcher checks only the roles each scenario starts.

## Module 03: remote teleoperation

Use the [WAN scenario guide](../modules/03-remote-teleoperation/README.md) to
choose hosts and configure the transport. Create a second **Full Security**
template for domain `1` with tag `medtech-wan`, using the committed
[TeleopWanDomain policy](../system/security/domain_scope/TeleopWanDomain/).
Use the same upload/create commands as for LAN, with a different governance
template name, and enroll only the roles for each host:

| App | LAN domain `0` | WAN domain `1` |
| --- | --- | --- |
| Active Routing Service | `RsActiveLan` | `RsActiveWan` |
| Passive Routing Service | `RsPassiveLan` | `RsPassiveWan` |
| Cloud Routing Service (relay scenario) | — | `RsCloudWan` |
| Cloud Discovery Service | — | Shared WAN PSK files only |

Use the proper domain template ID in each enrollment command. Keep both domain
trees under one artifact root on hosts that use both, and use the same local
deployment name for that host's LAN and WAN participants. WAN peers and Cloud
Discovery Service must use the same WAN PSK set. CDS does not need a Full
Security identity; deliver just the current and extra WAN PSK files to the CDS
host through your approved secret distribution process, or use the agent's
local WAN artifacts if CDS is colocated with an enrolled WAN participant.
Do not copy another host's identity key to provide CDS with the PSKs.

```bash
export MEDTECH_EPS_WAN_DOMAIN_TAG=medtech-wan
python medtech.py run --scenario teleop-or-side --security --provider eps
# On the controller host, use --scenario teleop-controller-side instead.
# On the cloud host, select the services used by your topology:
python medtech.py run 03-remote-teleoperation CdsCloud --security --provider eps
```

Set the root and deployment variables from the enrollment section on each
host; set the LAN tag on hosts with LAN participants. CDS-only launch uses the
WAN PSK files regardless of the deployment name. Do not assume that running
processes reload keys when the agent replaces files.

## Module 04: local only

Use `--provider local` for this walkthrough. Its deliberately separate trust
states are not ordinary enrolled roles in the trusted EPS deployment.
