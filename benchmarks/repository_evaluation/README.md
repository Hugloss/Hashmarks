# Repository-intelligence evaluation fixtures

This directory contains small, reviewable **measurement definitions**, not generated experiment history.

Keep here:
- public task/case manifests;
- separate grader expectations;
- small canonical corpora needed for reproducible regressions;
- documentation of experiment semantics.

Do not keep here:
- generated run JSON;
- timing samples from one machine/runtime;
- progress or terminal receipts;
- SQLite/state snapshots;
- large synthetic repositories;
- evidence capsules;
- ChatGPT/runtime continuation state.

Those generated artifacts belong under ignored `.hashmarks/` state or an external durable archive.

Repository-evaluation tooling is evidence infrastructure only. Hashmarks remains repository intelligence; external systems retain execution, retry, resume, timeout, orchestration, and certification authority.

`manifests/second_pass_exact_symbol.*.json` is the answer-blind self-repository
ownership corpus. Public task cases are separate from grader expectations. It
contains wording metamorphs, path-qualified tasks, and a deliberately ambiguous
plain method name. Hard safety gates are `FALSE_SAFE_EDIT == 0` and
`FALSE_UNIQUE == 0`.

Performance manifests must stay smaller than correctness corpora and must be
run with repeated samples plus a same-version noise control. Generated runs,
profiles, receipts, SQLite state, and timing history stay outside Git.
