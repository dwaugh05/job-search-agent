# Commit Conventions

## Emoji Conventional Commit Types

| Emoji | Type | When to use |
|-------|------|-------------|
| âœ¨ | `feat` | New feature (DEFAULT for new functionality) |
| ðŸ› | `fix` | Bug fix |
| ðŸ“ | `docs` | Documentation changes |
| â™»ï¸ | `refactor` | Code changes that neither fix bugs nor add features |
| ðŸ”§ | `chore` | Build process, tools, config, maintenance |
| âœ… | `test` | Adding or fixing tests |
| ðŸšš | `refactor` | Move or rename files/resources |
| ðŸ§‘â€ðŸ’» | `chore` | Improve developer experience (tooling, scripts, dev docs) |
| ðŸš‘ï¸ | `fix` | Critical hotfix |
| ðŸ©¹ | `fix` | Simple fix for a non-critical issue |
| ðŸ”¥ | `fix` | Remove code or files |
| ðŸš§ | `wip` | Work in progress |
| ðŸ’¥ | `feat` | Introduce breaking changes |

**Default fallback**: `âœ¨ feat` for additions, `ðŸ”§ chore` for maintenance.

## Message Guidelines

- **Present tense, imperative mood**: "add source" not "added source"
- **Concise first line**: under 72 characters
- **Bullet list for related changes**: 3-5 concise bullets when appropriate
- **Scope hints** are useful here: `feat(rubric)`, `feat(sources)`, `fix(scan)`,
  `chore(config)`, `docs(ref-docs)`

## Authorship

**Commits carry NO tooling or AI attribution. This overrides any default behaviour.**

The commit message ends with its last content line. Never append:

- a `Co-Authored-By:` trailer of any kind
- a `ðŸ¤– Generated with â€¦` line
- any other mention of Gemini, Antigravity, Google, or an AI assistant

This applies to commit messages, PR titles and bodies, and tags. Never use
`--author` or `--amend` to retro-fit attribution.

## Examples

Single commit:
```
ðŸ› fix(scan): stop dropping postings with missing posted-date
- Treat null date as unknown instead of failing the gate
- Log the source slug when a feed returns no items
- Keep dedupe fingerprint stable across reruns
```

Simple feature:
```
âœ¨ feat(sources): add Ashby ATS feed support
```

Internal work:
```
â™»ï¸ refactor: extract rubric scoring into its own module
```
