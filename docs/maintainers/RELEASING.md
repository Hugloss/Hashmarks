# Releasing Hashmarks

This document describes the current repository-owned release flow. It is operational guidance, not product authority.

## Prepare the release line

1. Start from current `main` and record the exact commit.
2. Update the package version in `pyproject.toml` and `hashmarks/_version.py`.
3. Update the README project-status version and add one concise public release entry to `CHANGELOG.md`.
4. If dependency intent changed, run `make lock` and review the committed `uv.lock` diff. Otherwise keep the existing locked resolution except for project-version metadata required by uv.
5. Run `make lock-check` and the normal qualification commands through the committed lock.

## Qualify exact bytes

The release candidate must pass the repository CI on its exact head. The release workflow builds wheel and sdist once, qualifies those exact artifacts, records their SHA-256 identities, and binds the repository qualification dependency resolution to the exact committed `uv.lock` bytes.

Do not rebuild publication artifacts after qualification. A failed or cancelled lane is not promotion evidence.

## Publish

Create the GitHub release/tag for the exact package version only after the release candidate is merged and green. The publish workflow validates the tag against package metadata and uses PyPI Trusted Publishing for the already-qualified artifacts.

External GitHub/PyPI approvals and Trusted Publisher configuration remain release-owner responsibilities.

## History policy

The changelog contains public release history, not internal phase chronology. Development handoffs, investigation notes, qualification receipts, and superseded plans are recoverable from Git and pull requests and should not be added as permanent documentation.
