---
name: gh-all-merge
description: "Smart one-shot GitHub workflow: commits and pushes to the working branch, then merges into master and pushes both branches."
argument-hint: "[branch-name]"
---

# Skill: gh-all-merge

**Smart one-shot GitHub workflow**: Commits and pushes the working branch, then
immediately merges into master and pushes both.

For commit message format, see [commit-conventions.md](commit-conventions.md).

## Usage

```
/gh-all-merge [branch-name]
```

If branch name is omitted, uses the current branch. If the current branch IS
master, just commit and push master — skip Step B.

---

## What This Skill Does

### Step A: Local PC → GitHub working branch

1. **Stage everything**: `git add -A`
   - Always include `ref-docs/`, `rubric/`, and `config/` (they are project source of truth)
   - Never stage `.venv/`, `__pycache__/`, or `data/*.bak-*` (covered by `.gitignore`)
2. **Analyze changes**: `git diff --stat` + file path analysis + recent conversation context
3. **Auto-decide commit strategy**: split if 2+ distinct features, single commit with bullets if related
4. **Generate commit messages**: emoji conventional format (see commit conventions link above)
5. **Execute commits** automatically
6. **Push to GitHub**: `git push origin [branch-name]`

### Step B: working branch → master (immediately after)

```bash
git checkout master
git merge [branch-name]
git push origin master
git checkout [branch-name]
```

---

## Decision Logic

### Split into Multiple Commits When:
- 2+ distinct features/systems (e.g., "add Greenhouse source" + "fix rubric weighting")
- Unrelated file path domains
- 10+ files with clearly different purposes

### Single Commit with Bullet List When:
- Related small fixes in the same area
- Files that work together (module + config + test)
- Small scope or all in one domain

---

## Important Notes

- **No quality checks**: this skill skips lint/type checks.
- **Never runs the app or a scan** as part of committing.
- **Never kills processes** — repo rule.
- **Returns to the working branch** after the merge.
