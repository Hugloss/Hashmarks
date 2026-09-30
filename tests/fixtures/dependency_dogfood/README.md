# Dependency-change dogfood corpus

The `absent`, `v1`, and `v2` states model adding `dummy-dep`, changing it from
1.0.0 to 2.0.0, and removing it. Tests consume only these checked-in bytes;
`~/Bolagsverket/code/tmp/dummy-dependency-fixtures` is optional scratch input,
not a CI dependency.

The uv `v1` and `v2` locks are byte-for-byte copies of genuine locks resolved
offline with uv 0.10.0 in the experimental corpus. The `absent` and `grouped`
locks were resolved offline with uv 0.12.17. `grouped` has no base dependency:
`dummy-dep` appears in one optional extra and one dev group. Each state includes
its source project files.

The Maven trees and lists were produced offline with Maven 3.8.7, Java 21, and
`maven-dependency-plugin` 3.9.0. The dogfood harness explicitly declares these
contexts semantically complete because the captures were generated without tree/list
include, exclude, scope, subtree, or transitive filtering. A temporary Maven repository held the cached
plugin tooling and a locally built dummy JAR: `jar --create --file <jar> --manifest
maven/dummy-dep-manifest.mf`, installed under `example.fixture:dummy-dep` at
1.0.0 and 2.0.0 with `maven-install-plugin` 2.4 `install-file`. For each POM,
`dependency:tree -DoutputType=json` produced `tree.json`, and
`dependency:list` produced `list.txt`; both used `-DoutputFile=<path>` and
`-Dstyle.color=never`. The trees are byte-for-byte command outputs; the lists
omit only a terminal empty line to satisfy Git whitespace checks. Maven's
`none` marker for an empty list and all resolved facts are preserved. No
dependency resolution happens in Hashmarks' adapters or in CI.


The Maven corpus also includes `maven/transitive-upgrade/{before,after}`, a
native Maven consumer capture for the real `io.minio:minio`
`8.5.17 -> 8.6.0` upgrade. It deliberately exercises a larger resolved graph:
26 dependency inventory entries before and 22 after, including direct version
changes, transitive version changes, component additions/removals, scope changes,
and relationship-topology churn. The named libraries are corpus provenance only;
tests use the capture to attack producer-neutral dependency observation and delta
behavior. Hashmarks contains no MinIO- or OkHttp-specific product rule. Exact
capture tooling and commands are retained in
`maven/transitive-upgrade/PROVENANCE.md` and `maven-version.txt`.

Run `make dependency-dogfood` for the add/version-change/remove and grouped-scope
checks. Synthetic parser-edge tests remain separate and do not claim to be
producer captures. The observations carry caller-claimed producer authority:
this corpus proves Hashmarks' translation and query behavior for these bytes,
not independent correctness of uv or Maven resolution.
