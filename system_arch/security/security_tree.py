"""DDS Security tree — config types, path conventions, and orchestration.

Defines a :class:`SecurityTree` for declaratively describing the CAs,
domain scopes, and identity modules of a DDS security system, plus
:func:`scaffold_tree` for one-time directory scaffolding and
:meth:`SecurityTree.generate_artifacts` for artifact generation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from fnmatch import fnmatch
import hashlib
import logging
import re
from pathlib import Path
from typing import Optional

from dds_security import (
    CA_CERT_VALIDITY_DAYS,
    extract_cert_dates,
    extract_subject_dn,
    generate_crl,
    generate_identity,
    generate_intermediate_ca,
    generate_psk_seed,
    generate_root_ca,
    render_template,
    scaffold_governance,
    scaffold_identity,
    scaffold_intermediate_ca,
    scaffold_permissions,
    scaffold_root_ca,
    sign_governance,
    sign_permissions,
)

log = logging.getLogger(__name__)


def detect_connext_version() -> tuple[int, ...] | None:
    """Detect the installed Connext version from the Python bindings.

    Returns a tuple like ``(7, 3, 0)`` or ``None`` if the bindings are not
    available.
    """
    try:
        import rti.connextdds as dds
        v = dds.ProductVersion.current
        return (v.major_version, v.minor_version, v.release_version)
    except Exception:
        return None


def _version_str(version: tuple[int, ...] | None) -> str:
    """Format a version tuple as a dotted string, e.g. ``'7.3.0'``."""
    if version:
        return ".".join(str(c) for c in version)
    return "0.0.0"


# ---------------------------------------------------------------------------
# Config types (plain data, no behavior)
# ---------------------------------------------------------------------------


@dataclass
class CA:
    name: str
    issuer: Optional['CA'] = None
    path: Optional[Path] = None
    alternatives: list['CA'] = field(default_factory=list)

    @property
    def self_signed(self) -> bool:
        return self.issuer is None


@dataclass
class TopicRule:
    """A single ``<topic_rule>`` entry in a DDS governance document."""
    topic_expression: str
    enable_discovery_protection: bool = False
    enable_liveliness_protection: bool = False
    enable_read_access_control: bool = True
    enable_write_access_control: bool = True
    metadata_protection_kind: str = "NONE"
    data_protection_kind: str = "NONE"


@dataclass
class Governance:
    name: str
    issuer: CA
    template: Optional[Path] = None       # override default governance.xml.j2
    domain_id_min: int = 0
    domain_id_max: Optional[int] = None   # None = no upper bound
    allow_unauthenticated_participants: bool = False
    enable_join_access_control: bool = True
    discovery_protection_kind: str = "SIGN"
    liveliness_protection_kind: str = "SIGN"
    rtps_protection_kind: str = "ENCRYPT"
    enable_key_revision: bool = True
    topic_rules: list[TopicRule] = field(default_factory=lambda: [
        TopicRule(topic_expression="*"),
        TopicRule(
            topic_expression="DDS:Security:LogTopicV2",
            enable_write_access_control=False,
            metadata_protection_kind="SIGN",
            data_protection_kind="ENCRYPT",
        ),
    ])


@dataclass
class Permissions:
    """DDS permissions configuration for a single participant.

    **Validity window design:** ``not_before`` / ``not_after`` are deliberately
    more forgiving (longer) than identity certificate lifetimes.  This ensures
    that rotating an identity certificate does not also require re-signing the
    permissions XML.  Connext 7.x enforces permissions expiration at runtime
    via the ``enable_key_revision`` governance setting.
    """
    name: str
    issuer: CA
    grant_name: str = ""                  # defaults to f"{name}Participant" at scaffold time
    domain_id: int = 0
    not_before: str = "2024-06-01T13:00:00"
    not_after: str = "2037-06-01T13:00:00"
    publish_topics: list[str] = field(default_factory=lambda: [
        "t/DeviceStatus",
        "t/DeviceHeartbeat",
        "DDS:Security:LogTopicV2",
    ])
    subscribe_topics: list[str] = field(default_factory=lambda: [
        "t/MotorControl",
        "t/DeviceCommand",
    ])
    subject_name_expression: Optional[str] = None
    # When set, emits <subject_name_expression> (Connext >= 7.4.0, POSIX
    # fnmatch case-sensitive pattern) instead of the auto-generated
    # <subject_name> exact-match DN.  The caller is responsible for
    # providing a correctly-cased value; unlike <subject_name>, the
    # expression match is case-sensitive.


@dataclass
class Identity:
    name: str
    issuer: CA


@dataclass
class DomainScope:
    name: str
    governance: Governance = None
    permissions: list[Permissions] = field(default_factory=list)
    psk_seeds: list['PskSeed'] = field(default_factory=list)


@dataclass
class App:
    name: str
    identities: list[Identity] = field(default_factory=list)


@dataclass
class PskSeed:
    """A Pre-Shared Key seed file entry for ``dds.sec.crypto.rtps_psk_secret_passphrase``.

    When generated, produces a file at ``<root>/<filename>`` containing
    ``<id>:<seed>`` as required by the Connext PSK passphrase property.

    **File format** (content written to disk)::

        <id>:<seed>

    **ID rules:**

    - Connext 7.3.x: valid range is 0–254.
    - Connext 7.6.0+: valid range is 0–4294967295 (least-significant byte != 0xFF).
    - Use **monotonically increasing IDs** on each rotation. Never change the
      seed without also changing the ID (Connext will reject it).

    **Rotation strategy — 7.3.0:**

    7.3.0 has no multi-PSK decode window. Rotate by updating this file to a new
    ``<id>:<seed>`` and distributing it to all hosts as quickly as possible. Expect
    transient decode failures and message loss during the mixed-key window. Build
    applications to tolerate transient communication disturbances.

    **Rotation strategy — 7.6.0+:**

    7.6.0 adds ``dds.sec.crypto.rtps_psk_secret_passphrase_extra`` for decode-only
    extra passphrases, enabling a zero-loss rolling transition::

        1. Set ``...passphrase_extra`` on all participants: old + new passphrases.
        2. Update ``...passphrase`` (primary) from old → new on all participants.
        3. Remove ``...passphrase_extra``.

    The ``WanCommonSecurityConfig`` QoS snippet includes a commented-out
    ``...passphrase_extra`` element ready to be activated when upgrading to 7.6.0+.

    Attributes:
        filename: Output file name relative to the domain scope directory
                  (e.g. ``TeleopWanDomain.psk`` → ``domain_scope/TeleopWanDomain/TeleopWanDomain.psk``).
                  Use a ``.psk`` extension (no RTI-mandated extension, but
                  ``.psk`` is clearer than ``.txt`` for operator awareness).
        id:       PSK ID written as the integer prefix. Must be in [0,254] for
                  Connext 7.3.x. Increment on every rotation; never reuse.
        length:   Seed length in characters (passed to :func:`generate_psk_seed`).
    """
    filename: str
    id: int = 0
    length: int = 64


@dataclass
class Module:
    name: str
    apps: list[App] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SecurityTree — declarative project structure + orchestration
# ---------------------------------------------------------------------------


@dataclass
class SecurityTree:
    """Declarative definition of a DDS security system.

    Directory layout produced::

        <root>/
        ├── ca/<ca_name>/
        │   ├── <ca_name>.cnf
        │   ├── private/<ca_name>.key
        │   ├── certs/<issuer>/<ca_name>.crt
        │   ├── newcerts/
        │   ├── index.txt
        │   └── serial
        ├── domain_scope/<scope>/
        │   ├── <psk_filename>.psk          (if PSK seeds defined)
        │   ├── governance/<name>/<name>.xml
        │   │                └── signed/<issuer>/<name>.p7s
        │   └── permissions/<role>/<role>.xml
        │                        └── signed/<issuer>/<role>.p7s
        └── identity/<module>/<app>/<participant>/
            ├── <participant>.cnf
            ├── private/<participant>.key
            └── certs/<issuer>/<participant>.crt
    """

    certificate_authorities: list[CA] = field(default_factory=list)
    domain_scopes: list[DomainScope] = field(default_factory=list)
    modules: list[Module] = field(default_factory=list)

    org_name: str = "Company Name"
    country: str = "US"
    state: str = "CA"
    email_domain: str = "company_name.com"
    connext_version: tuple[int, ...] | None = None
    copyright_year: int = 2024

    # -- Path conventions ---------------------------------------------------

    def _ca_dir(self, root: Path, ca_def: CA) -> Path:
        return ca_def.path if ca_def.path else root / "ca" / ca_def.name

    def _governance_dir(self, root: Path, scope_name: str, gov_name: str) -> Path:
        return root / "domain_scope" / scope_name / "governance" / gov_name

    def _permissions_dir(self, root: Path, scope_name: str, perm_name: str) -> Path:
        return root / "domain_scope" / scope_name / "permissions" / perm_name

    def _identity_dir(self, root: Path, module_name: str, app_name: str, id_name: str) -> Path:
        return root / "identity" / module_name / app_name / id_name

    # -- Artifact generation ------------------------------------------------

    def generate_artifacts(self, root: Path, force: bool = False,
                           strict: bool = False) -> None:
        """Generate all keys, certificates, and signed XML files.

        Args:
            root:   Root directory for artifact output.
            force:  Re-generate even if artifacts already exist.
            strict: Promote warnings to fatal errors.
        """

        warnings: list[str] = []

        def _warn(msg: str) -> None:
            """Log a warning; in strict mode, collect for later abort."""
            log.warning(msg)
            if strict:
                warnings.append(msg)

        def _check_strict() -> None:
            if warnings:
                raise RuntimeError(
                    f"--strict: aborting due to {len(warnings)} warning(s):\n"
                    + "\n".join(f"  - {w}" for w in warnings)
                )

        # --- Validation E: duplicate identity (name, issuer) pairs ---------
        seen_identities: set[tuple[str, str]] = set()
        for module in self.modules:
            for app in module.apps:
                for identity in app.identities:
                    pair = (identity.name, identity.issuer.name)
                    if pair in seen_identities:
                        _warn(
                            f"Duplicate identity ({identity.name!r}, "
                            f"issuer={identity.issuer.name!r}) across apps. "
                            "This may corrupt the CA index.txt or create "
                            "ambiguous DN matching in permissions."
                        )
                    seen_identities.add(pair)

        # --- Validation F: governance domain range covers permissions -------
        for scope in self.domain_scopes:
            gov = scope.governance
            gov_min = gov.domain_id_min
            gov_max = gov.domain_id_max  # None = unbounded
            for perm in scope.permissions:
                if perm.domain_id < gov_min:
                    _warn(
                        f"Permissions '{perm.name}' domain_id={perm.domain_id} "
                        f"is below governance '{gov.name}' domain_id_min={gov_min}."
                    )
                if gov_max is not None and perm.domain_id > gov_max:
                    _warn(
                        f"Permissions '{perm.name}' domain_id={perm.domain_id} "
                        f"exceeds governance '{gov.name}' domain_id_max={gov_max}."
                    )

        # --- Validation #14: stale scaffold hash --------------------------
        hash_file = root / ".scaffold-hash"
        if hash_file.is_file():
            expected = _compute_tree_hash(self)
            stored = hash_file.read_text().strip()
            if stored != expected:
                _warn(
                    "Scaffold hash mismatch — the tree definition has "
                    "changed since last --scaffold. Re-run --scaffold "
                    "to update committed config files."
                )

        _check_strict()

        ca_cert_cache: dict[str, Path] = {}

        def _ca_key(ca_def: CA) -> Path:
            cd = self._ca_dir(root, ca_def)
            return cd / "private" / f"{ca_def.name}.key"

        def _ca_cnf(ca_def: CA) -> Path:
            return self._ca_dir(root, ca_def) / f"{ca_def.name}.cnf"

        def _ca_cert(ca_def: CA, issuer: "CA | None" = None) -> Path:
            cd = self._ca_dir(root, ca_def)
            signer = issuer.name if issuer else ca_def.name
            return cd / "certs" / signer / f"{ca_def.name}.crt"

        def _reset_ca_state(ca_def: CA) -> None:
            """Reset CA index.txt and serial for deterministic output (#15)."""
            ca_dir = self._ca_dir(root, ca_def)
            index = ca_dir / "index.txt"
            serial = ca_dir / "serial"
            newcerts = ca_dir / "newcerts"
            # Ensure CA state files exist (needed by openssl ca -gencrl
            # and certificate signing even on a fresh run).
            newcerts.mkdir(parents=True, exist_ok=True)
            index.write_text("")
            serial.write_text("1000\n")

        def _check_prereqs(ca_def: CA) -> None:
            """Validation B: check prerequisite files exist."""
            cnf = _ca_cnf(ca_def)
            if not cnf.is_file():
                _warn(
                    f"CA config not found: {cnf} — "
                    "did you run --scaffold first?"
                )

        def _check_key_perms(key_path: Path) -> None:
            """Validation C: warn if key file permissions are too open."""
            if key_path.is_file():
                mode = key_path.stat().st_mode
                if mode & 0o177:
                    _warn(
                        f"Key file {key_path} has permissions "
                        f"{oct(mode & 0o777)}; expected 0o600 or stricter. "
                        f"Run: chmod 600 {key_path}"
                    )

        def _check_cert_validity(cert_path: Path, label: str,
                                 issuer_cert: Path | None = None) -> None:
            """Validations D and #4: expired cert and leaf-outlives-CA."""
            try:
                not_before, not_after = extract_cert_dates(cert_path)
            except Exception:
                return
            now = datetime.now(timezone.utc)
            if not_after <= now:
                _warn(f"{label} cert {cert_path.name} has already expired "
                      f"(Not After: {not_after.isoformat()}).")
            if issuer_cert and issuer_cert.is_file():
                try:
                    _, issuer_not_after = extract_cert_dates(issuer_cert)
                except Exception:
                    return
                if not_after > issuer_not_after:
                    _warn(
                        f"{label} cert {cert_path.name} expires "
                        f"{not_after.isoformat()} but its issuer expires "
                        f"{issuer_not_after.isoformat()}. The cert will be "
                        "unusable after the issuer expires."
                    )

        def _resolve_ca(ca_def: CA) -> Path:
            if ca_def.name in ca_cert_cache:
                return ca_cert_cache[ca_def.name]

            _check_prereqs(ca_def)
            _reset_ca_state(ca_def)
            _check_key_perms(_ca_key(ca_def))

            if ca_def.self_signed:
                cert = generate_root_ca(
                    _ca_key(ca_def), _ca_cnf(ca_def), _ca_cert(ca_def),
                    force=force,
                )
                _check_cert_validity(cert, f"Root CA '{ca_def.name}'")
            else:
                issuer_cert = _resolve_ca(ca_def.issuer)
                issuer_dir = self._ca_dir(root, ca_def.issuer)
                cert = generate_intermediate_ca(
                    _ca_key(ca_def), _ca_cnf(ca_def),
                    _ca_cert(ca_def, ca_def.issuer),
                    issuer_cnf=_ca_cnf(ca_def.issuer),
                    issuer_key=_ca_key(ca_def.issuer),
                    issuer_cert=issuer_cert,
                    issuer_cwd=issuer_dir,
                    days=CA_CERT_VALIDITY_DAYS,
                    force=force,
                )
                _check_cert_validity(cert, f"Intermediate CA '{ca_def.name}'",
                                     issuer_cert)

            ca_cert_cache[ca_def.name] = cert

            # Generate initial (empty) CRL for this CA (#7)
            ca_dir = self._ca_dir(root, ca_def)
            crl_path = ca_dir / "certs" / ca_def.name / f"{ca_def.name}.crl"
            generate_crl(
                _ca_cnf(ca_def), _ca_key(ca_def), cert, crl_path,
                cwd=ca_dir,
            )

            # Generate alternative CA bundle if alternatives are defined (#9)
            if ca_def.alternatives:
                bundle_path = ca_dir / "certs" / ca_def.name / f"{ca_def.name}-bundle.pem"
                parts = [cert.read_text()]
                for alt in ca_def.alternatives:
                    alt_cert = _resolve_ca(alt)
                    parts.append(alt_cert.read_text())
                bundle_path.write_text("".join(parts))
                log.info("CA bundle written: %s", bundle_path)

            return cert

        # CAs
        for ca_def in self.certificate_authorities:
            _resolve_ca(ca_def)

        # Governance & permissions
        for scope in self.domain_scopes:
            gov = scope.governance
            perm_ca_cert = _resolve_ca(gov.issuer)
            perm_ca_key = _ca_key(gov.issuer)
            gov_dir = self._governance_dir(root, scope.name, gov.name)

            # Validation B: check governance XML exists
            gov_xml = gov_dir / f"{gov.name}.xml"
            if not gov_xml.is_file():
                _warn(
                    f"Governance XML not found: {gov_xml} — "
                    "did you run --scaffold first?"
                )

            sign_governance(
                perm_ca_key, perm_ca_cert,
                gov_xml,
                gov_dir / "signed" / gov.issuer.name / f"{gov.name}.p7s",
                force=force,
            )

            for perm in scope.permissions:
                p_ca_cert = _resolve_ca(perm.issuer)
                p_ca_key = _ca_key(perm.issuer)
                perm_dir = self._permissions_dir(root, scope.name, perm.name)
                perm_xml = perm_dir / f"{perm.name}.xml"

                # Validation B: check permissions XML exists
                if not perm_xml.is_file():
                    _warn(
                        f"Permissions XML not found: {perm_xml} — "
                        "did you run --scaffold first?"
                    )

                sign_permissions(
                    p_ca_key, p_ca_cert,
                    perm_xml,
                    perm_dir / "signed" / perm.issuer.name / f"{perm.name}.p7s",
                    force=force,
                )

        # PSK seed files (per domain scope)
        for scope in self.domain_scopes:
            scope_dir = root / "domain_scope" / scope.name
            for psk in scope.psk_seeds:
                psk_file = scope_dir / psk.filename
                if not psk_file.is_file() or force:
                    psk_file.parent.mkdir(parents=True, exist_ok=True)
                    seed = generate_psk_seed(psk.length)
                    psk_file.write_text(f"{psk.id}:{seed}")
                    log.info("Generated PSK seed file: %s", psk_file)
                else:
                    log.info("PSK seed file exists, skipping: %s", psk_file)

        # Identities
        for module in self.modules:
            for app in module.apps:
                for identity in app.identities:
                    id_dir = self._identity_dir(
                        root, module.name, app.name, identity.name)
                    id_ca_dir = self._ca_dir(root, identity.issuer)
                    id_ca_cert = _resolve_ca(identity.issuer)

                    id_cnf = id_dir / f"{identity.name}.cnf"
                    id_key = id_dir / "private" / f"{identity.name}.key"
                    id_cert = id_dir / "certs" / identity.issuer.name / f"{identity.name}.crt"

                    # Validation B: check identity CNF exists
                    if not id_cnf.is_file():
                        _warn(
                            f"Identity config not found: {id_cnf} — "
                            "did you run --scaffold first?"
                        )

                    _check_key_perms(id_key)

                    generate_identity(
                        id_key, id_cnf, id_cert,
                        issuer_cnf=_ca_cnf(identity.issuer),
                        issuer_key=_ca_key(identity.issuer),
                        issuer_cert=id_ca_cert,
                        issuer_cwd=id_ca_dir,
                        force=force,
                    )

                    # Validation D / #4: cert validity
                    _check_cert_validity(
                        id_cert,
                        f"Identity '{identity.name}'",
                        id_ca_cert,
                    )

                    # Validation #1: subject name mismatch
                    self._validate_subject_name(
                        root, identity, module, app, _warn,
                    )

                    # Validation #5: permissions vs cert validity
                    self._validate_permissions_validity(
                        root, identity, module, app, id_cert, _warn,
                    )

        _check_strict()

    # -- Validation helpers -------------------------------------------------

    def _validate_subject_name(self, root: Path, identity, module, app,
                               warn_fn) -> None:
        """#1: Compare live cert DN against committed permissions XML."""
        id_dir = self._identity_dir(
            root, module.name, app.name, identity.name)
        cert_path = None
        # Find the cert under certs/<issuer>/
        certs_dir = id_dir / "certs"
        if certs_dir.is_dir():
            for issuer_dir in certs_dir.iterdir():
                candidate = issuer_dir / f"{identity.name}.crt"
                if candidate.is_file():
                    cert_path = candidate
                    break
        if not cert_path:
            return

        try:
            cert_dn = extract_subject_dn(cert_path)
        except Exception:
            return

        # Find matching permissions XML across all domain scopes
        for scope in self.domain_scopes:
            for perm in scope.permissions:
                if perm.name != identity.name:
                    continue
                perm_xml = (
                    self._permissions_dir(root, scope.name, perm.name)
                    / f"{perm.name}.xml"
                )
                if not perm_xml.is_file():
                    continue
                content = perm_xml.read_text()

                if perm.subject_name_expression:
                    # fnmatch-based validation (case-sensitive per RTI spec)
                    if not fnmatch(cert_dn, perm.subject_name_expression):
                        warn_fn(
                            f"Identity '{identity.name}' cert DN "
                            f"'{cert_dn}' does not match "
                            f"subject_name_expression "
                            f"'{perm.subject_name_expression}' in "
                            f"{perm_xml.name}."
                        )
                else:
                    # Extract <subject_name> from committed XML
                    m = re.search(
                        r"<subject_name>\s*(.*?)\s*</subject_name>",
                        content,
                    )
                    if m:
                        xml_dn = m.group(1)
                        if _normalize_dn(cert_dn) != _normalize_dn(xml_dn):
                            warn_fn(
                                f"Identity '{identity.name}' cert DN "
                                f"'{cert_dn}' does not match "
                                f"<subject_name> '{xml_dn}' in "
                                f"{perm_xml.name}."
                            )

    def _validate_permissions_validity(self, root: Path, identity, module, app,
                                       cert_path: Path, warn_fn) -> None:
        """#5: Compare permissions not_after against cert Not After."""
        if not cert_path.is_file():
            return
        try:
            _, cert_not_after = extract_cert_dates(cert_path)
        except Exception:
            return

        for scope in self.domain_scopes:
            for perm in scope.permissions:
                if perm.name != identity.name:
                    continue
                try:
                    perm_not_after = datetime.fromisoformat(perm.not_after)
                    if perm_not_after.tzinfo is None:
                        perm_not_after = perm_not_after.replace(
                            tzinfo=timezone.utc)
                except ValueError:
                    continue

                if perm_not_after < cert_not_after:
                    warn_fn(
                        f"Permissions '{perm.name}' expire "
                        f"{perm.not_after} but the identity cert "
                        f"expires {cert_not_after.isoformat()}. "
                        "The participant will lose authorization "
                        "before its cert expires."
                    )
                elif cert_not_after < perm_not_after:
                    log.info(
                        "Identity '%s' cert expires before permissions "
                        "(%s < %s) — expected (safer model).",
                        perm.name, cert_not_after.isoformat(),
                        perm.not_after,
                    )

    # -- Status / expiry check (#13) ----------------------------------------

    def check_status(self, root: Path, warn_days: int = 30) -> None:
        """Scan all generated certificates and report days-to-expiry."""
        now = datetime.now(timezone.utc)
        results: list[tuple[str, Path, int]] = []

        def _check(label: str, cert: Path) -> None:
            if not cert.is_file():
                return
            try:
                _, not_after = extract_cert_dates(cert)
            except Exception:
                log.warning("Could not parse dates for %s", cert)
                return
            days_left = (not_after - now).days
            results.append((label, cert, days_left))

        # CAs
        for ca_def in self.certificate_authorities:
            ca_dir = self._ca_dir(root, ca_def)
            signer = ca_def.issuer.name if ca_def.issuer else ca_def.name
            cert = ca_dir / "certs" / signer / f"{ca_def.name}.crt"
            _check(f"CA: {ca_def.name}", cert)

        # Identities
        for module in self.modules:
            for app in module.apps:
                for identity in app.identities:
                    id_dir = self._identity_dir(
                        root, module.name, app.name, identity.name)
                    cert = (id_dir / "certs" / identity.issuer.name
                            / f"{identity.name}.crt")
                    _check(f"Identity: {identity.name}", cert)

        # Sort by days remaining
        results.sort(key=lambda r: r[2])
        for label, cert, days_left in results:
            if days_left < 0:
                log.error("EXPIRED (%d days ago): %s — %s",
                          -days_left, label, cert)
            elif days_left <= warn_days:
                log.warning("Expiring in %d days: %s — %s",
                            days_left, label, cert)
            else:
                log.info("%d days remaining: %s", days_left, label)


def _normalize_dn(dn: str) -> str:
    """Normalize a distinguished name for case/order-insensitive comparison.

    Splits on ``/`` or ``,``, lowercases each ``key=value`` pair, strips
    whitespace, and returns a sorted frozenset-style string.
    """
    parts = re.split(r"[/,]", dn)
    parts = [p.strip().lower() for p in parts if "=" in p]
    return ",".join(sorted(parts))


# ---------------------------------------------------------------------------
# Scaffold (maintainer-only)
# ---------------------------------------------------------------------------


def scaffold_tree(tree: SecurityTree, root: Path,
                  templates_dir: Path | None = None,
                  strict: bool = False) -> None:
    """Create the directory scaffold and expand Jinja2 templates.

    **Maintainer-only.** Run this once when adding new CAs, identities, or
    domain scopes, then commit the generated files.  No OpenSSL calls are made.

    Args:
        tree:          The :class:`SecurityTree` to scaffold.
        root:          Root directory where artifacts will be written.
        templates_dir: Directory containing ``*.j2`` template files.  Defaults
                       to ``root / "templates"``.  Pass an explicit path when
                       sharing templates across modules (e.g. the threat module
                       pointing at ``system_arch/security/templates``).
        strict:        If ``True``, refuse to overwrite files that have been
                       hand-edited since the last scaffold.
    """
    templates = templates_dir or root / "templates"
    warnings: list[str] = []

    def _safe_render(template: Path, dest: Path, context: dict) -> None:
        """Render with Validation A: warn if hand-edits would be overwritten."""
        import jinja2 as _j2
        env = _j2.Environment(
            undefined=_j2.StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )
        new_content = env.from_string(template.read_text()).render(**context)
        if dest.is_file():
            old_content = dest.read_text()
            if old_content != new_content:
                log.warning(
                    "Overwriting %s — file differs from template output "
                    "(local edits will be lost).", dest)
                if strict:
                    warnings.append(f"Would overwrite hand-edited file: {dest}")
                    return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(new_content)

    for ca in tree.certificate_authorities:
        ca_dir = tree._ca_dir(root, ca)
        scaffold_root_ca(
            ca_dir,
            subdirs=["certs", "requests", "newcerts", "private"],
            index=ca_dir / "index.txt",
            serial=ca_dir / "serial",
        )
        _safe_render(
            templates / "ca.cnf.j2",
            ca_dir / f"{ca.name}.cnf",
            {
                "ca_name": ca.name,
                "common_name": ca.name,
                "org_name": tree.org_name,
                "email": f"{ca.name.lower()}@{tree.email_domain}",
                "country": tree.country,
                "state": tree.state,
            },
        )

    for scope in tree.domain_scopes:
        gov = scope.governance
        gov_tmpl = gov.template or templates / "governance.xml.j2"
        _safe_render(
            gov_tmpl,
            tree._governance_dir(root, scope.name, gov.name) / f"{gov.name}.xml",
            {
                "domain_id_min": gov.domain_id_min,
                "domain_id_max": gov.domain_id_max,
                "allow_unauthenticated_participants": gov.allow_unauthenticated_participants,
                "enable_join_access_control": gov.enable_join_access_control,
                "discovery_protection_kind": gov.discovery_protection_kind,
                "liveliness_protection_kind": gov.liveliness_protection_kind,
                "rtps_protection_kind": gov.rtps_protection_kind,
                "enable_key_revision": gov.enable_key_revision,
                "connext_version": tree.connext_version or (0, 0, 0),
                "connext_version_str": _version_str(tree.connext_version),
                "copyright_year": tree.copyright_year,
                "topic_rules": gov.topic_rules,
            },
        )

        for perm in scope.permissions:
            ver = tree.connext_version or (0, 0, 0)
            if perm.subject_name_expression and ver < (7, 4, 0):
                msg = (
                    f"Permissions '{perm.name}' uses subject_name_expression "
                    f"but Connext {_version_str(tree.connext_version)} < 7.4.0 "
                    f"does not support <subject_name_expression>. "
                    f"Falling back to <subject_name>."
                )
                log.warning(msg)
                if strict:
                    warnings.append(msg)
            subject_name = (
                f"/C={tree.country}/ST={tree.state}/O={tree.org_name}"
                f"/emailAddress={perm.name.lower()}@{tree.email_domain}/CN={perm.name}"
            )
            _safe_render(
                templates / "permissions.xml.j2",
                tree._permissions_dir(root, scope.name, perm.name) / f"{perm.name}.xml",
                {
                    "grant_name": perm.grant_name or f"{perm.name}Participant",
                    "subject_name": subject_name,
                    "subject_name_expression": perm.subject_name_expression,
                    "domain_id": perm.domain_id,
                    "not_before": perm.not_before,
                    "not_after": perm.not_after,
                    "publish_topics": perm.publish_topics,
                    "subscribe_topics": perm.subscribe_topics,
                    "connext_version": tree.connext_version or (0, 0, 0),
                    "connext_version_str": _version_str(tree.connext_version),
                    "copyright_year": tree.copyright_year,
                },
            )

    for module in tree.modules:
        for app in module.apps:
            for identity in app.identities:
                id_dir = tree._identity_dir(
                    root, module.name, app.name, identity.name)
                scaffold_identity(
                    id_dir / f"{identity.name}.cnf",
                    subdirs=["private", "certs"],
                )
                _safe_render(
                    templates / "identity.cnf.j2",
                    id_dir / f"{identity.name}.cnf",
                    {
                        "common_name": identity.name,
                        "org_name": tree.org_name,
                        "email": f"{identity.name.lower()}@{tree.email_domain}",
                        "country": tree.country,
                        "state": tree.state,
                    },
                )

    # Write scaffold hash sidecar (#14) for stale detection
    tree_hash = _compute_tree_hash(tree)
    hash_file = root / ".scaffold-hash"
    hash_file.write_text(tree_hash + "\n")

    if warnings:
        raise RuntimeError(
            f"--strict: scaffold aborted due to {len(warnings)} warning(s):\n"
            + "\n".join(f"  - {w}" for w in warnings)
        )


def _compute_tree_hash(tree: SecurityTree) -> str:
    """Compute a deterministic hash of the tree configuration for stale detection."""
    import json
    from dataclasses import asdict

    def _serialize(obj):
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, CA):
            return {"name": obj.name, "issuer": obj.issuer.name if obj.issuer else None}
        raise TypeError(f"Cannot serialize {type(obj)}")

    data = json.dumps(asdict(tree), default=_serialize, sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()[:16]
