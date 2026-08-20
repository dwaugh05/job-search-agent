---
name: gh-all-merge
description: >-
  Use this skill when the user asks to run "gh-all-merge" or asks to commit and push to github. 
  It provides a smart one-shot GitHub workflow: commits and pushes to the working branch, 
  then merges into master and pushes both branches.
---

# gh-all-merge

**Smart one-shot GitHub workflow**: Commits and pushes the working branch, then
immediately merges into master and pushes both.

For commit message formatting rules, you MUST read and follow: [commit-conventions.md](./references/commit-conventions.md).

## What This Skill Does

### Step A: Local PC → GitHub working branch

1. **Stage everything**: Run git add -A
   - Always include ef-docs/, ubric/, and config/ (they are project source of truth).
   - Never stage .venv/, __pycache__/, or data/*.bak-* (these should be covered by .gitignore).
2. **Analyze changes**: Run git status and git diff --stat (or git diff if needed) to understand what changed. Consider recent conversation context.
3. **Auto-decide commit strategy**: Split into multiple commits if there are 2+ distinct features. Use a single commit with bullets if changes are related.
4. **Generate commit messages**: Use emoji conventional format as defined in the commit conventions reference.
5. **Execute commits**: Run git commit for the staged changes.
6. **Push to GitHub**: Run git push origin <current-branch>. If you are currently on master, simply push and skip Step B.

### Step B: working branch → master (immediately after)

If you were on a branch other than master, run the following sequence to merge and push:

`ash
git checkout master
git merge <working-branch>
git push origin master
git checkout <working-branch>
`

## Decision Logic

### Split into Multiple Commits When:
- 2+ distinct features/systems (e.g., "add Greenhouse source" + "fix rubric weighting")
- Unrelated file path domains
- 10+ files with clearly different purposes

### Single Commit with Bullet List When:
- Related small fixes in the same area
- Files that work together (module + config + test)
- Small scope or all in one domain

## Important Notes

- **No quality checks**: Skip lint/type checks for this workflow.
- **Never run the app or a scan** as part of committing.
- **Never kill processes** — repo rule.
- **Return to the working branch** after the merge if Step B was executed.
- Make sure to execute the git commands in the terminal. Do not just output the plan to the user.
