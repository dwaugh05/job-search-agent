# Commit Conventions

## Emoji Conventional Commit Types

| Emoji | Type | When to use |
|-------|------|-------------|
| ✨ | `feat` | New feature (DEFAULT for new functionality) |
| 🐛 | `fix` | Bug fix |
| 📝 | `docs` | Documentation changes |
| ♻️ | `refactor` | Code changes that neither fix bugs nor add features |
| 🔧 | `chore` | Build process, tools, config, maintenance |
| ✅ | `test` | Adding or fixing tests |
| 🚚 | `refactor` | Move or rename files/resources |
| 🧑‍💻 | `chore` | Improve developer experience (tooling, scripts, dev docs) |
| 🚑️ | `fix` | Critical hotfix |
| 🩹 | `fix` | Simple fix for a non-critical issue |
| 🔥 | `fix` | Remove code or files |
| 🚧 | `wip` | Work in progress |
| 💥 | `feat` | Introduce breaking changes |

**Default fallback**: `✨ feat` for additions, `🔧 chore` for maintenance.

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
- a `🤖 Generated with …` line
- any other mention of Claude, Claude Code, Anthropic, or an AI assistant

This applies to commit messages, PR titles and bodies, and tags. Never use
`--author` or `--amend` to retro-fit attribution.

## Examples

Single commit:
```
🐛 fix(scan): stop dropping postings with missing posted-date
- Treat null date as unknown instead of failing the gate
- Log the source slug when a feed returns no items
- Keep dedupe fingerprint stable across reruns
```

Simple feature:
```
✨ feat(sources): add Ashby ATS feed support
```

Internal work:
```
♻️ refactor: extract rubric scoring into its own module
```
