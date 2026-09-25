# Releasing Hashmarks

Release preparation is a normal pull request. CI, not a local agent run, owns the required qualification.

## Release pull request

1. Update the version in `pyproject.toml`, `hashmarks/_version.py`, the README project status, and the project entry in `uv.lock`. Add a concise, substantive public entry to `CHANGELOG.md`. If dependency intent also changed, refresh the lock intentionally and review that diff.
2. Open a pull request and let CI (`.github/workflows/ci.yml`) run the configured checks. Local focused checks are useful when editing behavior, but a local `make release-check` or full-suite rerun is not required just for version, changelog, or documentation edits and does not replace CI.
3. Merge once the pull-request CI is green. The publish workflow independently qualifies the tagged merge commit.

## Publish

Create a GitHub release with tag `vX.Y.Z` pointing at the merged commit. The publish workflow (`.github/workflows/publish.yml`) validates the tag against the package version, runs its release checks, builds and smoke-tests the exact wheel and sdist, and publishes that same qualified artifact bundle through PyPI Trusted Publishing. A failed or cancelled publish workflow is not a completed release.

GitHub/PyPI approvals and Trusted Publisher configuration remain release-owner responsibilities.

## History policy

The changelog contains public release history, not internal phase chronology. Development handoffs, investigation notes, qualification receipts, and superseded plans are recoverable from Git and pull requests and should not be added as permanent documentation.
