# Hashmarks first-public-release qualification plan

This checklist prepares the exact Hashmarks release candidate for public inspection, packaging, tagging, and publication. It is release-process documentation, not product authority. It deliberately does **not** authorize new repository-intelligence features.

The release rule is simple:

> Qualify the smallest public product we already have. Fix release-surface defects and missing proof, but do not grow Hashmarks merely to make the first release look larger.

## Release blockers

A public release is blocked until every item in this section is closed on the exact release commit and exact release artifacts.

- [ ] Final public GitHub repository identity is known and stable.
- [ ] Final PyPI project name is confirmed and controlled by the release owner; configure a Trusted Publisher (a pending publisher is acceptable before first upload, but does not reserve the name).
- [ ] Root/package version, release notes, Git tag, and public documentation all describe the same release.
- [ ] Required GitHub checks are green on the exact release commit.
- [ ] Python 3.11, 3.12, 3.13, and 3.14 support is qualified for the advertised core surface.
- [ ] Optional MCP support is qualified with the real official SDK, from an installed distribution rather than only a source checkout.
- [ ] At least one real MCP host smoke passes against the installed release candidate; OpenCode is the primary host proof.
- [ ] Wheel, sdist, source release artifact, checksums, and qualification receipts are bound to the exact release commit and are not rebuilt after qualification for publication.
- [ ] Public vulnerability reporting is usable before publication.
- [ ] Post-publication install/metadata/provenance smoke succeeds against the bytes actually served by PyPI.

## 1. Freeze scope and exact continuation authority

- [ ] Use exact persisted HM312 as the source parent.
- [ ] Treat any release-surface edits as one bounded public-release closure candidate; do not reopen product architecture phases without new evidence of an in-profile defect.
- [ ] Record parent source SHA-256, candidate source identity, producer identity, selection input identity, and qualification-plan identity.
- [ ] Record every source change from HM312 in one patch and prove exact patch replay.
- [ ] Keep the five-tool, local-stdio, read-only MCP product boundary unchanged unless native evidence proves a correctness defect.
- [ ] Preserve the rule that hosted/environmental MCP skips are SKIP/ENVIRONMENT_BLOCKED, never silently relabeled PASS.

## 2. Public repository presentation and onboarding

- [ ] Root `README.md` explains the product before internal mechanics or release history.
- [x] Add a public-user install path (`pip install hashmarks`) before source-checkout development instructions once the package is publishable.
- [ ] Keep `pip install "hashmarks[mcp]"` as the optional MCP path and keep core runtime dependencies empty.
- [x] Make `docs/GETTING_STARTED.md` distinguish **install/use from PyPI** from **develop/qualify from source**; public users should not need `make init` merely to try Hashmarks.
- [ ] Run every README/Getting Started command that is intended for a new user from a clean installed wheel, outside the source tree.
- [ ] `docs/README.md` clearly separates current contracts from historical development evidence.
- [ ] `PRODUCT_BOUNDARY.md` and `AGENTS.md` state the agent/execution non-goals.
- [ ] `.github/CONTRIBUTING.md`, `.github/SECURITY.md`, issue forms, and pull-request template are present.
- [ ] Validate all relative Markdown links and important public external links on the exact release tree.
- [ ] No private usernames, machine names, company-local paths, credentials, tokens, internal repository URLs, transient state, or unpublished secrets are retained.
- [ ] Historical evidence is clearly labeled non-normative.

## 3. Changelog and public release-history consistency

- [ ] Put `Unreleased` at the top of the public changelog until the release is actually cut.
- [ ] Keep the top-level `CHANGELOG.md` user-facing. Move/collapse HM engineering chronology that belongs in `docs/development/` rather than presenting phase archaeology as the public release history.
- [ ] Verify the `0.13.0` and `0.14.0` headings against actual published/tagged history before claiming “Initial public release” or a completed release.
- [ ] Record the Apache-2.0 and optional MCP changes in the correct public release section.
- [ ] Ensure README version text, `pyproject.toml`, `hashmarks/_version.py`, changelog release heading, and Git tag agree exactly.
- [ ] Add the release date only when the release is actually cut; do not fabricate historical dates.

## 4. Package/repository metadata

- [x] Root `LICENSE` contains Apache License 2.0 and matches the package SPDX/license metadata.
- [ ] After the final GitHub repository URL is known, add `[project.urls]` metadata to `pyproject.toml` (Repository, Issues, Documentation as applicable).
- [x] Apache-2.0 is declared through the SPDX expression plus `license-files = ["LICENSE"]`; the build backend projects both into wheel/sdist metadata and includes the license file.
- [ ] Confirm package version in `pyproject.toml`, `hashmarks/_version.py`, and the first README heading agree.
- [ ] Confirm package name ownership/availability and the Trusted Publisher identity before the first irreversible PyPI upload.
- [ ] Build wheel/sdist and inspect Core Metadata, entry point, optional extra, license metadata/file, `Requires-Python`, classifiers, project URLs, and long description rendering.
- [ ] Confirm `uv.lock` is gitignored local state and absent from release artifacts; record the actual uv/pytest/Ruff/MCP versions used in release evidence.
- [ ] Confirm the wheel contains only installed product files plus required metadata/license.

## 5. Decide and lock the sdist policy

HM313 v12 closes the pre-public broad-sdist decision: the PyPI sdist is now an intentional buildable public-source package rather than a mirror of the development checkout. Tests, benchmarks, qualification scripts, `AGENTS.md`, Makefile, and `docs/development/` archaeology remain repository-only.

- [x] Classify each sdist root as **required to build**, **useful source-release material**, or **repository-only development history**.
- [x] Prefer the smallest sdist that still builds the exact wheel and contains the required source/license/readme/build metadata.
- [x] Retain only current public docs deliberately; tests, benchmarks, qualification scripts, and `docs/development/` history are repository-only and excluded from the PyPI sdist.
- [x] Add an exact sdist member-contract test so accidental future bloat is detected.
- [x] Prove the trimmed sdist builds and installs in an isolated environment with no source checkout available.
- [x] Record wheel/sdist member counts and byte sizes in release evidence (v12 hosted packaging receipt: wheel 118 members / 356,934 bytes; sdist 137 members / 354,409 bytes).

## 6. Python and qualification-tool compatibility

- [ ] Repository-owned CI passes on Python 3.11, 3.12, 3.13, and 3.14.
- [ ] Run an **installed-wheel smoke** on every advertised Python version, not only source-tree tests.
- [x] Keep `pytest >=8.4` as policy only if the true floor is qualified. CI now has a real `pytest==8.4.0` boundary job because `>=8.4` admits 8.4.0.
- [ ] Keep a latest/current pytest job to detect forward incompatibility.
- [ ] Keep Ruff minimum (`0.12.0`) and current/latest diagnostic jobs with the explicit rule contract.
- [ ] Keep uv minimum (`0.10.0`) and current/latest qualification.
- [ ] Record exact observed tool versions in the final receipt; exact CI inputs are evidence, not public dependency pins.

## 7. Platform support decision

The package metadata currently advertises Python support but does not state an OS support envelope, while documentation recommends Linux/WSL for watcher/daemon behavior.

Before release, choose one explicit contract:

- [ ] **Portable-core contract:** add Windows and macOS installed-wheel/core smoke in CI, while documenting Linux/WSL as the native watcher/performance qualification surface; **or**
- [ ] **Linux/WSL initial-support contract:** state that limitation clearly in README/Getting Started/package metadata so Windows/macOS users are not left to infer support from `py3-none-any` alone.
- [ ] Whichever contract is chosen, exercise path handling, temporary state, cleanup, and CLI startup on every advertised platform.

## 8. Native MCP compatibility and installed-artifact proof

Source-tree MCP tests are necessary but not enough for a package release.

- [ ] Dedicated native `mcp-interop` runs with the official `mcp>=2.2.0` SDK and no hosted skip.
- [ ] Test the declared minimum MCP line (`mcp==2.2.0`) and the current/latest SDK separately. Exact versions here are qualification inputs, not package-policy pins.
- [ ] Verify whether the `hashmarks[mcp]` extra is installable and functional on every advertised Python version; if the optional SDK has a narrower Python envelope, document that explicitly instead of allowing an accidental install-time surprise.
- [ ] Build the wheel first, create a clean environment, then install the **wheel with its `mcp` extra** (or the wheel plus the exact resolved SDK) and run MCP interop outside the source tree.
- [ ] Direct official SDK `list_tools` and `call_tool` pass with all five expected tools and read-only annotations.
- [ ] Real stdio initialize/discover/list/call/error behavior passes with the installed artifact.
- [ ] Prompts/resources remain empty unless a future explicit product decision adds them.
- [ ] Invalid tool inputs fail cleanly without traceback leakage or partial/stale result payloads.
- [ ] Server stdout remains protocol-clean; diagnostics/logging do not corrupt stdio framing.
- [ ] EOF, normal close, client cancellation, SIGTERM/process exit, and repeated start/stop do not leak a child process, lock, or corrupted state.

## 9. Real MCP host proof

- [ ] Install the candidate wheel into the host-visible environment.
- [ ] OpenCode starts `hashmarks --workspace <repo> mcp` with the documented project-local config.
- [ ] `opencode mcp list` (or equivalent current host inspection) reports the server connected.
- [ ] The host can discover exactly the five Hashmarks tools and successfully call at least `repository_context`, `find`, `task_evidence`, and one post-change flow.
- [ ] Verify the documented `protocol: "auto"` behavior against the OpenCode version used for the release receipt; record the host version because host protocol behavior can change independently of Hashmarks.
- [ ] Prefer one independent Pi/second-host smoke when practical, but do not add host-specific code to Hashmarks to make that pass.

## 10. Release stress and adversarial qualification

All stress tests operate on disposable repositories or temporary installed environments. Do not mutate the frozen parent/archive.

### Concurrency/freshness

- [ ] Re-run the HM312 MCP concurrency test as an independent release receipt rather than relying on an earlier conversational claim.
- [ ] Exercise mixed `repository_context`, `find`, `task_evidence`, `change_impact`, and `post_change` calls with 32+ concurrent callers.
- [ ] Mutate, delete, recreate, rename, and replace repository files while reads are active.
- [ ] Assert zero incomplete `BUILDING` generations escape to consumers.
- [ ] Assert generation/freshness never moves backward and unknown/stale evidence is never strengthened to fresh/current.
- [ ] Prove old `task_evidence` is rejected or correctly marked when the bound generation no longer applies.
- [ ] Prove `task_evidence -> repository edit -> post_change` continuity on the current generation.

### Input/path abuse

- [ ] Empty, huge, malformed, Unicode, absolute, traversal, symlink, deleted-path, and renamed-path inputs fail or resolve according to the documented repository boundary.
- [ ] Oversized limits/queries stay bounded and do not produce unbounded output/memory growth.
- [ ] Malformed previous-evidence payloads cannot gain current evidence status.

### Lifecycle/resource stability

- [ ] Repeat open/call/close cycles and record file-descriptor/process/RSS growth.
- [ ] Run deterministic fixed-seed repetitions so a PASS is reproducible, not luck from one scheduling interleaving.
- [ ] Record p50/p95/p99 latency only as diagnostics; latency must not weaken correctness assertions.
- [ ] Add a larger synthetic repository run (for example 10k+ files) to ensure MCP serialization does not introduce pathological release-scale behavior; do not turn this into a new performance feature phase unless a measured defect appears.

## 11. Core artifact qualification

- [ ] `make init`
- [ ] `make test-profile`
- [ ] `make release-check`
- [ ] `make artifact-check ARTIFACT_PYTHON=3.14` on a host with Python 3.14 available.
- [ ] Build wheel and sdist independently twice from clean extractions and compare SHA-256 byte identity.
- [x] Build a wheel from the sdist and compare it with the direct wheel; the stdlib backend reproduces the wheel byte-identically.
- [ ] Exact source artifact built independently twice with identical SHA-256.
- [ ] Exact artifact extracted and focused release surface re-qualified.
- [ ] Persisted artifact read back byte-identically.
- [ ] No `.venv`, `.pytest_cache`, `__pycache__`, `.hashmarks`, bytecode, secrets, or machine-local state in release artifacts.
- [x] Import/CLI smoke runs from outside the source checkout and exercises the generated `hashmarks` console script against a disposable repository.

## 12. CI and release-workflow supply-chain hardening

- [x] Add bounded `timeout-minutes` to long-running qualification jobs so a deadlock cannot consume an unbounded CI run.
- [x] Keep workflow permissions minimal; ordinary CI remains `contents: read`, and CI checkout does not persist Git credentials.
- [x] Pin third-party GitHub Actions to immutable commit SHAs with human-readable version comments; regression tests reject mutable action tags.
- [ ] Optionally enable Dependabot/Renovate for GitHub Actions pins so immutable action references remain maintainable.
- [x] Add a dedicated release workflow triggered only by a published GitHub Release; the tag must exactly match the package version.
- [ ] Use a protected GitHub `pypi` environment with manual approval for the publication job when available.
- [x] The release workflow uses PyPI Trusted Publishing/OIDC and contains no long-lived PyPI token input. PyPI-side Trusted Publisher registration remains an external blocker.
- [x] The publish job consumes the **already-qualified build artifacts** from the build job and revalidates their manifest/hashes; it does not rebuild wheel/sdist.
- [x] The release bundle retains a canonical release manifest plus SHA-256 checksums beside the exact wheel/sdist.
- [x] The trusted publication action requests PyPI attestations and prints published hashes; post-publication attestation readback remains required.

HM313 v13 closes the repository-owned publication workflow contract: third-party actions are immutable-SHA pinned, jobs are time-bounded, CI checkout credentials are not persisted, the MCP compatibility matrix includes the exact `mcp==2.2.0` floor plus a current line through an installed wheel, and the publish job receives and re-verifies the exact build-job artifacts. A successful Hashmarks promotion-evidence manifest is explicitly **not** release authorization; final release authority remains the external release process.

## 13. Security and dependency-supply review

- [ ] GitHub private vulnerability reporting is enabled, or a real private security contact is documented before publication.
- [ ] Re-run secret/private-path scanning against the exact release source, wheel, and sdist.
- [ ] Record the resolved dependency graph for the optional MCP extra used in release qualification.
- [ ] Check the optional MCP dependency set for known high-severity vulnerabilities at release time; perform this as release evidence, not as a new Hashmarks runtime subsystem.
- [ ] Verify no build/publish step executes repository code beyond the explicit build backend/qualification commands expected by the release process.
- [ ] Document how to yank a bad PyPI release and issue a patch release; do not rely on deleting/replacing immutable published files.

## 14. Product-boundary review

- [ ] No new feature was admitted solely because it is useful to an agent or Oh-Goon.
- [ ] New production capabilities have an ADMIT/SPLIT/REJECT record.
- [ ] Hashmarks remains repository intelligence, not the agent solution loop.
- [ ] Hashmarks remains repository intelligence, not Oh-Goon's execution/certification motor.
- [ ] Historical compatibility surfaces have not been presented as recommended architecture.
- [ ] MCP remains transport only: no file editing, shell/process execution, git/worktree lifecycle, test execution, planning/retry/recovery, model calls, remote tenancy, or hidden host-specific workflow state.

## 15. Evidence-backed public claims

Public differentiation should come from measured repository-intelligence behavior, not a broader feature list.

- [ ] Re-run a small, stable release benchmark set on the exact candidate for any numbers shown publicly (cold/warm/hot map economics, one-edit refresh, bounded evidence size, retrieval/correctness metrics as applicable).
- [ ] Do not present historical v0.10/v0.11 benchmark numbers as current 0.14.0 results unless clearly labeled historical.
- [ ] Bind every headline performance/correctness claim to a retained methodology + receipt.
- [ ] Keep competitor comparisons factual and reproducible; do not add competitor-specific behavior to production code.
- [ ] Preserve the distinctive product story: dependency-free core, bounded repository evidence, explicit freshness/provenance, ambiguity instead of false certainty, change-impact/post-change continuity, read-only host-neutral MCP, and no agent/execution takeover.

## 16. Final first-time-user review

Read the repository and installed package as a first-time visitor:

1. Can you explain Hashmarks after the first screen of the README?
2. Can you install and run it without cloning the repository?
3. Can you install the MCP extra and connect the documented host without reading development history?
4. Can you tell which APIs are current versus historical/experimental?
5. Can you tell what Hashmarks deliberately does **not** own?
6. Can you find contribution, security, architecture, integration, and changelog guidance in one or two clicks?
7. Does every command shown to a normal user work from the installed package rather than only from the source checkout?
8. Does the public package contain only material we intentionally chose to publish?

## 17. Publication and post-publication verification

- [ ] Freeze the exact release commit and tag. Do not change source after the final qualification receipt.
- [ ] Publish the exact qualified wheel/sdist bytes through Trusted Publishing; no rebuild in the publish job.
- [ ] Create the GitHub release from the same tag and attach checksums/selected qualification evidence as appropriate.
- [ ] Fetch the wheel/sdist back from PyPI and compare SHA-256 with the pre-publication artifacts.
- [ ] Verify PyPI displays the expected Apache-2.0 metadata, Python requirement, project URLs, long description, and optional `mcp` extra.
- [ ] Verify PyPI provenance/attestation is present for each published distribution.
- [ ] In clean Python 3.11 and 3.14 environments, install `hashmarks==<release>` from PyPI and run core CLI/import smoke.
- [ ] Install `hashmarks[mcp]==<release>` from PyPI and run official-SDK stdio smoke plus the primary real-host smoke again.
- [ ] Confirm the GitHub release/tag, PyPI release, changelog, and repository default branch all point users to the same public contract.
- [ ] Only after these checks succeed mark the release record complete.

## Explicit non-blocking follow-ups

These are useful but should not delay the first release unless testing exposes a real defect:

- a second MCP host beyond the primary OpenCode proof;
- broader marketing/benchmark material beyond a small reproducible headline set;
- macOS/Windows native watcher implementations when the portable-core/Linux-watcher contract is already explicit;
- SBOM generation beyond the recorded optional-MCP dependency graph;
- additional MCP tools, remote HTTP transport, resources, prompts, or host-specific integrations;
- new repository-intelligence primitives not required to fix a demonstrated release correctness issue.

## Release stop conditions

Stop publication and return to a bounded fix/requalification cycle if any of the following occurs:

- stale/unknown evidence is surfaced as fresh/current;
- repository/path isolation is violated;
- native MCP protocol output is corrupted or exposes partial generations;
- the installed wheel/sdist behaves differently from the qualified source in a contract-relevant way;
- a supported Python/platform/SDK boundary cannot install or execute the advertised surface;
- artifact hashes change between qualification and publication;
- a secret/private path or unintended internal development artifact is found in the publish set;
- public docs instruct users to run a command that does not work on the installed package;
- publication identity (Git tag/GitHub/PyPI/project URL) is inconsistent.
