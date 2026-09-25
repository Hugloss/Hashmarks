# Releasing Hashmarks

Hashmarks uses one reviewed release pull request and one automatic Publish workflow. CI owns qualification; `main` remains the single long-lived source authority.

## Normal release

Prepare the mechanical release edits with one command:

```bash
make release-prepare VERSION=X.Y.Z
```

That command:

- updates `pyproject.toml`, `hashmarks/_version.py`, and the README package version;
- resets `.github/release-request.toml` to a normal release request containing only the new version, so an old retry `source_sha` or `publication_attempt` cannot leak into a new release;
- inserts a deliberately non-publishable `Development` section at the top of `CHANGELOG.md`;
- refreshes and checks the committed `uv.lock`.

Then replace the `Development` changelog heading and placeholder bullet with concise public release notes. Review the diff and run:

```bash
make release-check
```

Open the release pull request. Merge only after qualification convergence is green. The release-request merge SHA becomes the default release source authority.

## What pull-request CI proves

Normal PR CI qualifies the release-relevant product surfaces before merge:

- supported Python and package artifacts;
- the standalone Linux x86_64 executable and the public shell installer used by Linux and WSL2;
- the standalone Windows x86_64 executable and the public PowerShell installer;
- CLI and MCP startup from each native standalone;
- install/upgrade behavior and version identity;
- native standalone qualification receipts binding executable bytes, checksum sidecars, platform, architecture, and reported version.

WSL intentionally uses the Linux executable and installer. It is not a third mirrored build.

## Automatic publication

Changing `.github/release-request.toml` on `main` triggers `.github/workflows/publish.yml`.

For a normal release, the reviewed release-request merge SHA becomes the release-source authority. Publish then:

1. verifies that exact source is reachable from current `main`;
2. re-runs locked release qualification;
3. builds and smoke-tests the exact wheel and sdist;
4. builds and natively smoke-tests the Linux/WSL standalone;
5. builds and natively smoke-tests the Windows standalone;
6. produces a native qualification receipt for each standalone;
7. downloads the qualified bundles into the publication job and revalidates their bytes and receipts;
8. creates one final publication manifest binding the exact source SHA, wheel, sdist, both standalone executables, both installer checksum sidecars, and both native qualification identities;
9. verifies any existing release tag still resolves to the exact release-source SHA;
10. creates a draft GitHub Release, uploads only the qualified public assets, and publishes the draft after all checks pass.

Hashmarks publishes these qualified artifacts through GitHub Releases. The release workflow does not automatically publish to PyPI. A failed or cancelled Publish run is not a completed release.

The public GitHub Release contains:

- `hashmarks-X.Y.Z-py3-none-any.whl`;
- `hashmarks-X.Y.Z.tar.gz`;
- `hashmarks-linux-x86_64`;
- `hashmarks-linux-x86_64.sha256`;
- `hashmarks-windows-x86_64.exe`;
- `hashmarks-windows-x86_64.exe.sha256`;
- `release-manifest.json`;
- `SHA256SUMS.txt`.

## Post-publish end-user smoke

After a Windows-capable release is published, verify the public install paths from clean shells.

Linux or WSL2:

```bash
curl -fsSL https://raw.githubusercontent.com/Hugloss/Hashmarks/main/install.sh | sh
hashmarks --version
```

Native Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/Hugloss/Hashmarks/main/install.ps1 | iex
hashmarks --version
```

Both installers download the matching release executable and checksum sidecar, verify the candidate, run the candidate version smoke, and only then replace an existing installation.

Do not advertise a platform in public onboarding until a published release actually contains that platform's qualified assets.

## Publication retry

If publication infrastructure fails after the release source was approved, repair the publication machinery through a normal pull request. Keep the original release content immutable by changing the reviewed release request to:

```toml
version = "X.Y.Z"
source_sha = "<exact-reviewed-release-source-sha>"
publication_attempt = 2
```

Increment `publication_attempt` for each subsequent retry.

`source_sha` owns release content identity. `publication_attempt` only creates an auditable new publication attempt. Newer workflow machinery may perform the retry, but it must qualify, tag, and publish the explicitly requested source bytes.

The next normal release should always start with `make release-prepare VERSION=...`, which removes retry-only fields.

## History policy

The changelog contains public release history, not internal phase chronology. Development handoffs, investigation notes, qualification receipts, and superseded plans remain in Git and pull requests rather than the maintained product documentation.
