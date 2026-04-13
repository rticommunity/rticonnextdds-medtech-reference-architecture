#!/usr/bin/env python3
"""DDS Security artifact generation — primitives and DDS Security workflow.

Two layers:

Primitives — fully-parameterized, thin OpenSSL wrappers with no path
conventions baked in:
    openssl_run, render_template, generate_key, generate_csr, self_sign,
    sign_csr, sign_xml, revoke_cert, generate_crl, extract_subject_dn

DDS Security workflow — higher-level functions named after the DDS Security
workflow operations; each groups one or more primitives:
    (a)   scaffold_root_ca          set up root CA dirs and files
    (b)   generate_root_ca          generate root CA key + self-signed cert
    (c)   scaffold_intermediate_ca  set up intermediate CA dirs and files
    (d-f) generate_intermediate_ca  intermediate CA key + CSR + signed cert
    (g)   scaffold_identity         set up identity directory
    (h-j) generate_identity         identity key + CSR + signed cert
    (k)   revoke_certificate        revoke a cert; optionally regenerate CRL
    (l)   scaffold_governance       scaffold governance XML from a template
    (m)   sign_governance           S/MIME-sign governance XML
    (n)   scaffold_permissions      scaffold permissions XML from a template
    (o)   sign_permissions          S/MIME-sign permissions XML
    (p)   generate_psk_seed         random PSK passphrase seed
"""

import base64
import logging
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CA_CERT_VALIDITY_DAYS = 7300
IDENTITY_CERT_VALIDITY_DAYS = 730
EC_CURVE = "prime256v1"

_openssl = shutil.which("openssl")

# ===========================================================================
# Layer 1 — Primitives
# ===========================================================================


def openssl_run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run an OpenSSL command, raising on failure with stderr captured."""
    if not _openssl:
        raise EnvironmentError("openssl not found in PATH")
    kwargs.setdefault("check", True)
    kwargs.setdefault("stdout", subprocess.PIPE)
    kwargs.setdefault("stderr", subprocess.PIPE)
    log.debug("openssl %s", " ".join(str(a) for a in args))
    result = subprocess.run([_openssl, *args], **kwargs)
    if result.stderr:
        log.debug("openssl stderr: %s", result.stderr.decode().strip())
    return result


def render_template(template: Path, dest: Path,
                    context: dict | None = None) -> None:
    """Render a Jinja2 template file to *dest* using *context*.

    Uses ``StrictUndefined`` so typos in variable names raise immediately
    rather than silently producing empty strings.

    Requires the ``jinja2`` package (``pip install jinja2``).  The import is
    deferred so that callers who never invoke scaffolding functions do not
    need jinja2 installed.
    """
    import jinja2

    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    content = env.from_string(template.read_text()).render(**(context or {}))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)


def generate_key(key_path: Path, *, ec_curve: str = EC_CURVE) -> Path:
    """Generate an EC private key at *key_path* (no-op if it already exists)."""
    if key_path.is_file():
        return key_path
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.parent.name == "private":
        key_path.parent.chmod(0o700)
    openssl_run([
        "genpkey", "-algorithm", "EC",
        "-pkeyopt", f"ec_paramgen_curve:{ec_curve}",
        "-out", str(key_path),
    ])
    key_path.chmod(0o600)
    return key_path


def generate_csr(key_path: Path, cnf: Path, out_csr: Path) -> Path:
    """Generate a certificate signing request (CSR)."""
    out_csr.parent.mkdir(parents=True, exist_ok=True)
    openssl_run([
        "req", "-new",
        "-config", str(cnf),
        "-key", str(key_path),
        "-out", str(out_csr),
    ])
    return out_csr


def self_sign(key_path: Path, cnf: Path, out_cert: Path, *,
              days: int = CA_CERT_VALIDITY_DAYS,
              extensions: str = "v3_ca") -> Path:
    """Self-sign a certificate from *key_path* using *cnf*."""
    out_cert.parent.mkdir(parents=True, exist_ok=True)
    openssl_run([
        "req", "-x509", "-new",
        "-config", str(cnf),
        "-key", str(key_path),
        "-extensions", extensions,
        "-days", str(days),
        "-out", str(out_cert),
    ])
    return out_cert


def sign_csr(ca_cnf: Path, ca_key: Path, ca_cert: Path,
             csr: Path, out_cert: Path, *,
             extensions: str = "usr_cert",
             extfile: Path | None = None,
             days: int = IDENTITY_CERT_VALIDITY_DAYS,
             startdate: str | None = None,
             enddate: str | None = None,
             cwd: Path | None = None) -> Path:
    """Sign *csr* with a CA and write the signed certificate to *out_cert*.

    Args:
        ca_cnf:     CA's OpenSSL config file.
        ca_key:     CA's private key.
        ca_cert:    CA's certificate (used as the issuer cert).
        csr:        Certificate signing request to sign.
        out_cert:   Output path for the signed certificate.
        extensions: Extension section name to apply (default ``usr_cert``).
        extfile:    File from which to read extensions (e.g. the subject's
                    own config file).  When ``None``, extensions are read
                    from *ca_cnf*.
        days:       Certificate validity period in days.  Ignored when
                    *enddate* is provided.
        startdate:  Certificate ``notBefore`` in ``YYMMDDHHMMSSZ`` format.
        enddate:    Certificate ``notAfter`` in ``YYMMDDHHMMSSZ`` format.
                    Overrides *days* when set.
        cwd:        Working directory for ``openssl ca``.  Set to the CA
                    directory when the CA config uses ``dir = .``.
    """
    out_cert.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ca",
        "-config", str(ca_cnf),
        "-in", str(csr),
        "-out", str(out_cert),
        "-batch", "-notext",
        "-cert", str(ca_cert),
        "-keyfile", str(ca_key),
        "-extensions", extensions,
    ]
    if enddate is not None:
        cmd += ["-enddate", enddate]
    else:
        cmd += ["-days", str(days)]
    if startdate is not None:
        cmd += ["-startdate", startdate]
    if extfile is not None:
        cmd += ["-extfile", str(extfile)]
    openssl_run(cmd, cwd=str(cwd) if cwd else None)
    return out_cert


def sign_xml(key_path: Path, cert_path: Path,
             xml_path: Path, out_p7s: Path) -> Path:
    """Sign *xml_path* using S/MIME v3.2 (required by RTI Connext Security Plugins)."""
    out_p7s.parent.mkdir(parents=True, exist_ok=True)
    openssl_run([
        "smime", "-sign",
        "-in", str(xml_path),
        "-signer", str(cert_path),
        "-inkey", str(key_path),
        "-text",
        "-out", str(out_p7s),
    ])
    return out_p7s


def revoke_cert(ca_cnf: Path, ca_key: Path, ca_cert: Path,
                cert_path: Path, *,
                cwd: Path | None = None) -> None:
    """Revoke *cert_path* in the CA's ``index.txt`` database."""
    openssl_run([
        "ca", "-revoke", str(cert_path),
        "-config", str(ca_cnf),
        "-cert", str(ca_cert),
        "-keyfile", str(ca_key),
    ], cwd=str(cwd) if cwd else None)


def generate_crl(ca_cnf: Path, ca_key: Path, ca_cert: Path,
                 out_crl: Path, *,
                 cwd: Path | None = None) -> Path:
    """Generate a Certificate Revocation List (CRL) from the CA database."""
    out_crl.parent.mkdir(parents=True, exist_ok=True)
    openssl_run([
        "ca", "-gencrl",
        "-config", str(ca_cnf),
        "-cert", str(ca_cert),
        "-keyfile", str(ca_key),
        "-out", str(out_crl),
    ], cwd=str(cwd) if cwd else None)
    return out_crl


def extract_subject_dn(cert_path: Path) -> str:
    """Extract the RFC 2253 subject DN from a certificate.

    Useful for populating ``<subject_name>`` in DDS permissions files, where
    RTI Connext requires an exact string match with the certificate DN.
    """
    result = openssl_run([
        "x509", "-subject", "-nameopt", "RFC2253", "-noout",
        "-in", str(cert_path),
    ])
    # Output: "subject=CN=Arm,O=Company Name,ST=CA,C=US"
    line = result.stdout.decode().strip()
    return line.split("=", 1)[1] if "=" in line else line


def extract_cert_dates(cert_path: Path) -> tuple[datetime, datetime]:
    """Extract the Not Before / Not After dates from a certificate.

    Returns ``(not_before, not_after)`` as timezone-aware UTC datetimes.
    """
    result = openssl_run([
        "x509", "-noout", "-startdate", "-enddate",
        "-in", str(cert_path),
    ])
    lines = result.stdout.decode().strip().splitlines()
    # notBefore=Apr  8 12:00:00 2024 GMT
    # notAfter=Apr  6 12:00:00 2044 GMT
    dates = {}
    for line in lines:
        key, _, val = line.partition("=")
        dates[key.strip()] = val.strip()
    fmt = "%b %d %H:%M:%S %Y %Z"
    not_before = datetime.strptime(dates["notBefore"], fmt).replace(tzinfo=timezone.utc)
    not_after = datetime.strptime(dates["notAfter"], fmt).replace(tzinfo=timezone.utc)
    return not_before, not_after


# ===========================================================================
# Layer 2 — DDS Security workflow
# ===========================================================================


def scaffold_root_ca(ca_dir: Path, *,
                     cnf: Path | None = None,
                     subdirs: list[str] | None = None,
                     index: Path | None = None,
                     serial: Path | None = None) -> None:
    """(a) Scaffold a root CA directory for use with ``openssl ca``.

    All keyword arguments are optional; ``None`` means skip that component.

    Args:
        ca_dir:  CA base directory (always created).
        cnf:     Path where the CA config will be written — only the parent
                 directory is created here; write the file via
                 :func:`render_template`.
        subdirs: Subdirectory names to create inside *ca_dir*.  ``"private"``
                 is always created with mode ``0o700``; others use ``0o755``.
        index:   Path to ``index.txt``; touched if not present.
        serial:  Path to ``serial``; written as ``"1000"`` if not present.
    """
    ca_dir.mkdir(parents=True, exist_ok=True)

    if subdirs is not None:
        for d in subdirs:
            (ca_dir / d).mkdir(
                exist_ok=True, mode=0o700 if d == "private" else 0o755)

    if cnf is not None:
        cnf.parent.mkdir(parents=True, exist_ok=True)

    if index is not None:
        index.touch(exist_ok=True)

    if serial is not None:
        if not serial.is_file() or serial.stat().st_size == 0:
            serial.write_text("1000\n")


def generate_root_ca(key_path: Path, cnf: Path, out_cert: Path, *,
                     days: int = CA_CERT_VALIDITY_DAYS,
                     force: bool = False) -> Path:
    """(b) Generate a root CA private key and self-signed certificate."""
    if out_cert.is_file() and not force:
        log.info("Root CA cert exists, skipping: %s", out_cert)
        return out_cert
    generate_key(key_path)
    return self_sign(key_path, cnf, out_cert, days=days)


def scaffold_intermediate_ca(ca_dir: Path, *,
                              cnf: Path | None = None,
                              subdirs: list[str] | None = None,
                              index: Path | None = None,
                              serial: Path | None = None) -> None:
    """(c) Scaffold an intermediate CA directory.

    Identical parameters to :func:`scaffold_root_ca`.
    """
    scaffold_root_ca(ca_dir, cnf=cnf, subdirs=subdirs, index=index, serial=serial)


def generate_intermediate_ca(key_path: Path, cnf: Path, out_cert: Path, *,
                              issuer_cnf: Path,
                              issuer_key: Path,
                              issuer_cert: Path,
                              issuer_cwd: Path | None = None,
                              days: int = CA_CERT_VALIDITY_DAYS,
                              force: bool = False) -> Path:
    """(d-f) Generate an intermediate CA: private key, CSR, and signed certificate."""
    if out_cert.is_file() and not force:
        log.info("Intermediate CA cert exists, skipping: %s", out_cert)
        return out_cert
    generate_key(key_path)
    csr = out_cert.with_suffix(".csr")
    generate_csr(key_path, cnf, csr)
    sign_csr(issuer_cnf, issuer_key, issuer_cert, csr, out_cert,
             extensions="v3_ca", extfile=cnf, days=days, cwd=issuer_cwd)
    csr.unlink(missing_ok=True)
    return out_cert


def scaffold_identity(cnf_dest: Path, *,
                      subdirs: list[str] | None = None) -> None:
    """(g) Scaffold an identity directory.

    Creates the parent directory of *cnf_dest* and any *subdirs* within it.
    The config file itself is written separately via :func:`render_template`.
    ``"private"`` is created with mode ``0o700``; others use ``0o755``.
    """
    cnf_dest.parent.mkdir(parents=True, exist_ok=True)
    if subdirs is not None:
        for d in subdirs:
            (cnf_dest.parent / d).mkdir(
                exist_ok=True, mode=0o700 if d == "private" else 0o755)


def generate_identity(key_path: Path, cnf: Path, out_cert: Path, *,
                      issuer_cnf: Path,
                      issuer_key: Path,
                      issuer_cert: Path,
                      issuer_cwd: Path | None = None,
                      days: int = IDENTITY_CERT_VALIDITY_DAYS,
                      chain: bool = True,
                      force: bool = False) -> Path:
    """(h-j) Generate an identity: private key, CSR, and signed certificate.

    When *chain* is ``True`` (default), also writes ``<name>.chain.pem``
    containing the leaf cert concatenated with the issuer cert.  This is the
    file that should be referenced as ``dds.sec.auth.identity_certificate``
    in RTI Connext participant properties when the Identity CA is an
    intermediate (not directly the root).
    """
    if out_cert.is_file() and not force:
        log.info("Identity cert exists, skipping: %s", out_cert)
        return out_cert
    generate_key(key_path)
    csr = out_cert.with_suffix(".csr")
    generate_csr(key_path, cnf, csr)
    sign_csr(issuer_cnf, issuer_key, issuer_cert, csr, out_cert,
             extensions="usr_cert", extfile=cnf, days=days, cwd=issuer_cwd)
    csr.unlink(missing_ok=True)
    if chain:
        chain_path = out_cert.with_suffix(".chain.pem")
        chain_path.write_text(
            out_cert.read_text() + issuer_cert.read_text()
        )
    return out_cert


def generate_expired_identity(key_path: Path, cnf: Path, out_cert: Path, *,
                              issuer_cnf: Path,
                              issuer_key: Path,
                              issuer_cert: Path,
                              issuer_cwd: Path | None = None,
                              chain: bool = True,
                              force: bool = False) -> Path:
    """Generate an identity cert that is already expired (notAfter in the past).

    Uses the same private key as the normal identity (reuses *key_path* if it
    exists).  The certificate validity window is set entirely in the past
    (one year ago → one day ago) so that Connext rejects it at participant
    creation time.
    """
    if out_cert.is_file() and not force:
        log.info("Expired identity cert exists, skipping: %s", out_cert)
        return out_cert
    generate_key(key_path)
    csr = out_cert.with_suffix(".csr")
    generate_csr(key_path, cnf, csr)
    # One year ago → one day ago (YYMMDDHHMMSSZ)
    from datetime import datetime, timedelta, timezone
    one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)
    one_day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    startdate = one_year_ago.strftime("%y%m%d%H%M%SZ")
    enddate = one_day_ago.strftime("%y%m%d%H%M%SZ")
    sign_csr(issuer_cnf, issuer_key, issuer_cert, csr, out_cert,
             extensions="usr_cert", extfile=cnf,
             startdate=startdate, enddate=enddate,
             cwd=issuer_cwd)
    csr.unlink(missing_ok=True)
    if chain:
        chain_path = out_cert.with_suffix(".chain.pem")
        chain_path.write_text(
            out_cert.read_text() + issuer_cert.read_text()
        )
    return out_cert


def revoke_certificate(cert_path: Path, *,
                       issuer_cnf: Path,
                       issuer_key: Path,
                       issuer_cert: Path,
                       out_crl: Path | None = None,
                       issuer_cwd: Path | None = None) -> Path | None:
    """(k) Revoke a certificate and optionally regenerate the CRL.

    Returns the CRL path if *out_crl* is provided, otherwise ``None``.
    """
    revoke_cert(issuer_cnf, issuer_key, issuer_cert, cert_path, cwd=issuer_cwd)
    if out_crl is not None:
        return generate_crl(issuer_cnf, issuer_key, issuer_cert, out_crl,
                            cwd=issuer_cwd)
    return None


def scaffold_governance(template: Path, out_xml: Path,
                        context: dict | None = None) -> None:
    """(l) Scaffold a governance XML file from *template*."""
    render_template(template, out_xml, context)


def sign_governance(key_path: Path, cert_path: Path,
                    xml_path: Path, out_p7s: Path, *,
                    force: bool = False) -> Path:
    """(m) Sign a governance XML with S/MIME v3.2."""
    if out_p7s.is_file() and not force:
        log.info("Signed governance exists, skipping: %s", out_p7s)
        return out_p7s
    return sign_xml(key_path, cert_path, xml_path, out_p7s)


def scaffold_permissions(template: Path, out_xml: Path,
                         context: dict | None = None) -> None:
    """(n) Scaffold a permissions XML file from *template*."""
    render_template(template, out_xml, context)


def sign_permissions(key_path: Path, cert_path: Path,
                     xml_path: Path, out_p7s: Path, *,
                     force: bool = False) -> Path:
    """(o) Sign a permissions XML with S/MIME v3.2."""
    if out_p7s.is_file() and not force:
        log.info("Signed permissions exists, skipping: %s", out_p7s)
        return out_p7s
    return sign_xml(key_path, cert_path, xml_path, out_p7s)


def generate_psk_seed(length: int = 64) -> str:
    """(p) Generate a random PSK seed for ``dds.sec.crypto.rtps_psk_secret_passphrase``.

    Returns a URL-safe Base64-encoded string of exactly *length* characters.
    All characters are ASCII-printable and non-space, satisfying RTI Connext
    requirements (codes 32–126, first/last not spaces).

    RTI requires up to 512 printable ASCII characters.  For 256-bit entropy,
    at least 47 truly random characters are needed (~6 bits per Base64 char);
    the default length of 64 provides ~384 bits of entropy.

    Args:
        length: Seed length in characters (1–512).
    """
    if not 1 <= length <= 512:
        raise ValueError(f"PSK seed length must be between 1 and 512, got {length}")
    # Encode enough random bytes so that the base64 output is ≥ length chars.
    raw = base64.urlsafe_b64encode(secrets.token_bytes(length)).decode("ascii")
    # Strip padding '=' and trim to exactly length characters.
    return raw.rstrip("=")[:length]
