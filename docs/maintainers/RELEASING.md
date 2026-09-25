# Releasing Hashmarks

Release preparation and promotion are reviewed pull requests. CI owns qualification; `main` remains the single long-lived source authority.

## Release pull request

1. Update the version in `pyproject.toml`, `hashmarks/_version.py`, the README project status, and the project entry in `uv.lock`. Add a concise, substantive public entry to `CHANGELOG.md`. If dependency intent also changed, refresh the lock intentionally and review that diff.
2. Set `.github/release-request.toml` to the intended version:
   ```toml
   version = "X.Y.Z"
   ```
3. Open the release pull request and let CI (`.github/workflows/ci.yml`) run the configured checks, including the MCP-enabled release-profile lane and standalone CLI/MCP qualification.
4. Merge only after qualification convergence is green. The release-request merge SHA becomes the default release source authority.

## Publish

Merging a pull request that changes `.github/release-request.toml` triggers `.github/workflows/publish.yml` on `main`.

The Publish workflow:

1. reads the reviewed release request;
2. resolves and verifies the exact release-source SHA;
3. qualifies that source with the locked test and MCP environment;
4. builds and smoke-tests the exact wheel and sdist;
5. builds and smoke-tests the standalone Linux x86_64 CLI/MCP executable;
6. binds the qualified bytes with manifests and SHA-256 checksums;
7. verifies the downloaded qualified bundles again;
8. verifies the release tag resolves to the exact release-source SHA;
9. creates/uploads a draft GitHub Release and publishes it only after all checks pass.

Hashmarks publishes these qualified artifacts through GitHub Releases. The release workflow does not automatically publish to PyPI. A failed or cancelled Publish workflow is not a completed release.

## Publication retry

If publication infrastructure fails after the release source has already been approved, repair the publication machinery through a normal pull request. Preserve the original release source by adding its exact SHA to the reviewed release request and incrementing an auditable retry counter:

```toml
version = "X.Y.Z"
source_sha = "<reviewed-release-source-sha>"
publication_attempt = 2
```

`source_sha` owns release content identity. `publication_attempt` only retriggers publication and does not participate in release identity. The repaired workflow may come from newer `main`, but it must qualify, tag, and publish the explicitly requested source bytes.

## History policy

The changelog contains public release history, not internal phase chronology. Development handoffs, investigation notes, qualification receipts, and superseded plans are recoverable from Git and pull requests and should not be added as permanent documentation.
