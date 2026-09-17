from __future__ import annotations

DIGEST_ALGORITHM = "sha256"
IDENTITY_SCHEMA = "fastidentity.identity.v1"
FILE_IDENTITY_SCHEMA = "fastidentity.file.v1"
DIRECTORY_IDENTITY_SCHEMA = "fastidentity.directory.v1"
MANIFEST_SCHEMA = "fastidentity.input-manifest.v1"
INPUT_ROOT_SCHEMA = "fastidentity.input-root.v1"
SNAPSHOT_SCHEMA = "fastidentity.snapshot.v1"
DAEMON_PROTOCOL_VERSION = 3
DAEMON_SEMANTICS = "fastidentity.daemon-semantics.v3"
DAEMON_CAPABILITIES = (
    "repository-observation.v1",
    "registered-manifest.v1",
    "step-identity.v1",
)
