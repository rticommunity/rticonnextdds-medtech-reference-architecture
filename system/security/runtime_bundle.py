# (c) 2026 Copyright, Real-Time Innovations, Inc. (RTI) All rights reserved.
# Licensed under the terms in LICENSE.

"""Stage already issued local credentials into a fresh Full Security bundle."""

from __future__ import annotations

import filecmp
import re
import shutil
import tempfile
from pathlib import Path

from dds_security import openssl_run
from security_tree import CA, SecurityTree


def deployment_name(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value) or value.endswith("."):
        raise ValueError(f"Invalid deployment name: {value!r}")
    return value


def bundle_files(
    tree: SecurityTree,
    workspace: Path,
    identity_ca: CA,
    deployment: str,
    domain_ids: dict[str, int],
) -> dict[Path, Path]:
    """Map runtime-relative paths to files; never include private CA state."""
    deployment = deployment_name(deployment)
    identities = {
        identity.name: (module.name, app.name, identity)
        for module in tree.modules
        for app in module.apps
        for identity in app.identities
    }

    def ca_cert(ca: CA) -> Path:
        issuer = ca.issuer.name if ca.issuer else ca.name
        return tree._ca_dir(workspace, ca) / "certs" / issuer / f"{ca.name}.crt"

    files = {}
    domains = set()
    for scope in tree.domain_scopes:
        domain_id = domain_ids[scope.name]
        if domain_id < 0 or domain_id in domains:
            raise ValueError(f"Invalid or duplicate domain ID: {domain_id}")
        domains.add(domain_id)
        domain = Path(str(domain_id))
        governance = scope.governance
        permissions_ca = governance.issuer
        files[domain / "identity_ca.crt"] = ca_cert(identity_ca)
        files[domain / "permissions_ca.crt"] = ca_cert(permissions_ca)
        files[domain / "governance.p7s"] = (
            tree._governance_dir(workspace, scope.name, governance.name)
            / "signed"
            / permissions_ca.name
            / f"{governance.name}.p7s"
        )
        if len(scope.psk_seeds) > 2:
            raise ValueError(f"More than two PSKs configured for {scope.name}")
        for seed, name in zip(scope.psk_seeds, ("psk_secret.key", "psk_secret_extra.key")):
            files[domain / name] = workspace / "domain_scope" / scope.name / seed.filename
        for grant in scope.permissions:
            module, app, identity = identities[grant.name]
            if identity.issuer != identity_ca or grant.issuer != permissions_ca:
                raise ValueError(f"CA mismatch for {grant.name} in {scope.name}")
            role = domain / deployment / grant.name
            source = tree._identity_dir(workspace, module, app, identity.name)
            files[role / "identity.crt"] = (
                source / "certs" / identity_ca.name / f"{identity.name}.chain.pem"
            )
            files[role / "identity.key"] = source / "private" / f"{identity.name}.key"
            files[role / "permissions.p7s"] = (
                tree._permissions_dir(workspace, scope.name, grant.name)
                / "signed"
                / permissions_ca.name
                / f"{grant.name}.p7s"
            )
    return files


def stage_bundle(files: dict[Path, Path], destination: Path) -> bool:
    """Publish a complete new generation; never overwrite a live generation."""
    missing = [
        source for source in files.values() if not source.is_file() or not source.stat().st_size
    ]
    if missing:
        raise FileNotFoundError(
            f"Missing issued artifacts: {', '.join(map(str, sorted(set(missing))))}"
        )
    if destination.exists() or destination.is_symlink():
        if (
            destination.is_dir()
            and not destination.is_symlink()
            and all(
                (destination / relative).is_file()
                and filecmp.cmp(source, destination / relative, shallow=False)
                for relative, source in files.items()
            )
        ):
            return False
        raise FileExistsError(f"Bundle already exists at {destination}; stage to a new directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".bundle-") as tmp:
        staging = Path(tmp) / "bundle"
        staging.mkdir(mode=0o700)
        for relative, source in files.items():
            path = staging / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, path)
            path.chmod(0o600 if path.name.endswith(".key") else 0o644)
        validate_bundle(staging, files)
        staging.rename(destination)
    return True


def validate_bundle(root: Path, files: dict[Path, Path]) -> None:
    """Verify local demo key pairs, identity trust, and pinned policy signatures."""
    for relative in sorted(files):
        path = root / relative
        domain = root / relative.parts[0]
        if relative.name == "identity.crt":
            certificate = openssl_run(["x509", "-in", str(path), "-pubkey", "-noout"])
            key = openssl_run(["pkey", "-in", str(path.with_name("identity.key")), "-pubout"])
            if certificate.stdout != key.stdout:
                raise ValueError(f"Identity certificate and key do not match: {relative.parent}")
            openssl_run(
                ["verify", "-partial_chain", "-trusted", str(domain / "identity_ca.crt"), str(path)]
            )
        elif path.suffix == ".p7s":
            openssl_run(
                [
                    "smime",
                    "-verify",
                    "-noverify",
                    "-nointern",
                    "-in",
                    str(path),
                    "-certfile",
                    str(domain / "permissions_ca.crt"),
                ]
            )
