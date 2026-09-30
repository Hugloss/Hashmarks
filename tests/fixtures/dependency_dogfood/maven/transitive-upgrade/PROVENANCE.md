# Transitive-upgrade Maven capture provenance

This is a real native Maven consumer capture used as dependency dogfood.
The consumer declares one direct dependency: `io.minio:minio`.

- before: `8.5.17`
- after: `8.6.0`
- dependency plugin: `org.apache.maven.plugins:maven-dependency-plugin:3.9.0`
- tree: `dependency:tree -DoutputType=json -DoutputFile=tree.json -Dstyle.color=never`
- inventory: `dependency:list -DoutputFile=list.txt -Dstyle.color=never`

MinIO and its dependency names are corpus provenance only. Hashmarks product
semantics and assertions must remain producer-neutral and package-neutral.
