# Security policy

## Reporting a vulnerability

Please do **not** publish exploit details, credentials, private repository data, or other sensitive material in a public GitHub issue.

Use GitHub's private vulnerability reporting / Security Advisory flow for this repository. The public-release checklist requires private reporting to be enabled, or a concrete private security contact to be documented before publication.

Include enough information to reproduce and assess the issue without including unrelated sensitive data:

- affected Hashmarks version/commit;
- operating system and runtime version;
- minimal reproduction steps;
- affected trust/authority boundary;
- expected versus observed behavior;
- whether the issue can cross repository/worktree/process/consumer boundaries.

## Security-relevant areas

Hashmarks is primarily a repository-intelligence system. Security-sensitive defects include, among others:

- stale or forged repository evidence being accepted as current;
- path escape or repository-boundary violations;
- cross-worktree or cross-repository mutable-state leakage;
- malformed external evidence gaining authority;
- producer/identity/provenance validation bypass;
- untrusted repository declarations being promoted to trusted authority;
- accidental transfer of execution/admission/certification authority into Hashmarks.

Hashmarks does not claim to sandbox or securely execute arbitrary repository code. Process execution, sandboxing, admission, network/resource policy, and certification belong to an external execution system such as Oh-Goon.
