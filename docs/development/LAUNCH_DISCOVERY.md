# Launch discovery checklist

Status: repository-only launch guidance. This file is not part of the public source distribution and does not define product behavior.

Hashmarks should launch as its own product category and problem statement. Do not lead with competitor comparisons, rankings, or "better than" claims. Discovery should come from a consistent description of what Hashmarks actually does.

## Canonical one-sentence description

Use this sentence, or a close surface-specific shortening, across GitHub, PyPI, MCP Registry, release notes, and launch posts:

> **Local repository intelligence and a read-only MCP server for coding agents: codebase search, symbols, ownership, change impact, freshness, and verification evidence.**

## GitHub About description

Recommended repository description:

> Local repository intelligence and a read-only MCP server for coding agents. Codebase search, ownership, change impact, freshness, and verification evidence.

Do not spend the GitHub description on implementation details, phase/version history, qualification mechanics, or comparisons.

## GitHub topics

Use a focused set of high-intent topics. GitHub allows up to 20; relevance matters more than filling the limit.

Recommended launch topics:

- `repository-intelligence`
- `model-context-protocol`
- `mcp`
- `mcp-server`
- `coding-agents`
- `ai-coding`
- `code-intelligence`
- `code-search`
- `code-navigation`
- `repository-analysis`
- `change-impact`
- `impact-analysis`
- `dependency-analysis`
- `static-analysis`
- `developer-tools`
- `local-first`
- `python`

Host names such as Claude Code, Codex, OpenCode, and Pi belong naturally in README/integration documentation. Add host-specific GitHub topics only if they remain accurate and useful rather than using the topic list as keyword stuffing.

## Search language to keep consistent

Primary phrases should appear naturally in the README title, opening paragraphs, headings, package metadata, and integration docs:

- repository intelligence
- MCP server for coding agents
- local MCP server
- codebase search for coding agents
- code navigation
- repository analysis
- change impact analysis
- code ownership
- repository freshness
- verification evidence

Secondary integration phrases:

- Claude Code MCP server
- Codex MCP server
- OpenCode MCP server
- Pi MCP server
- Model Context Protocol code analysis

Do not repeat phrases mechanically. The product description should remain readable to a person who has never heard of Hashmarks.

## README first-screen contract

Before architecture, internals, benchmarks, or maintainer qualification, a new visitor should be able to answer:

1. What is Hashmarks?
2. What problem does it solve?
3. Does it run locally?
4. Is it an MCP server?
5. Which coding-agent hosts can use it?
6. How do I install and try it?

The install path should remain visible without scrolling through maintainer material:

```bash
pip install hashmarks
hashmarks --workspace . map sync
hashmarks --workspace . orient
hashmarks --workspace . find "where is this behavior owned?"
```

The MCP path should remain equally concrete:

```bash
pip install "hashmarks[mcp]"
hashmarks --workspace . mcp
```

## PyPI metadata

Keep `project.description` concise and aligned with the canonical description. Keep `project.keywords` focused on real user-search concepts such as repository intelligence, MCP, coding agents, codebase search/navigation, impact analysis, and developer tooling.

Once the final public repository URL is known, add `[project.urls]` for at least:

- Repository
- Documentation
- Issues
- Changelog

Do not invent these URLs before the public location is final.

## MCP Registry metadata

When publishing to the official MCP Registry, keep the server name and summary aligned with the README/PyPI description. The registry entry should link back to the canonical repository documentation rather than introducing a second product description.

## Social preview

Create a clean GitHub social-preview image after the public repository name/URL is final. Suggested visible copy:

> **Hashmarks**
> Repository intelligence for coding agents
> Local • read-only MCP • codebase search • change impact

The image should support the textual description, not contain information that exists nowhere in text.

## Discovery loop after launch

Search engines primarily need crawlable, useful text and links pointing to it. After the repository is public:

1. publish the PyPI package and link it to the repository;
2. publish the official MCP Registry entry and link it to the repository;
3. create a GitHub Release with a concise user-facing description;
4. use the same canonical repository URL in technical launch posts and documentation;
5. link directly to useful documentation pages with descriptive anchor text;
6. keep README/docs current rather than accumulating old launch copy above current behavior.

The goal is not artificial SEO. The goal is to make every public surface unambiguously describe the same useful product using the language users naturally search for.
