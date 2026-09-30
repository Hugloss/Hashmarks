# Maven multi-module dogfood provenance

Native Maven reactor capture with alpha and beta observed as separate
Hashmarks contexts. Alpha changes one selected external dependency;
beta depends on alpha and therefore observes the propagated transitive
change. External library identities are corpus provenance only.
