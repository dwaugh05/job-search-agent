---
description: One-shot git — stage everything, auto-write emoji commit(s), and push/merge to master for Career-Ops.
argument-hint: "[optional commit-message hint]"
---

Do all the GitHub commit + push + merge work for this repo in one shot by
following the **gh-all-merge** skill (`.claude/skills/gh-all-merge/SKILL.md`) —
invoke it now and carry out its steps exactly.

`$ARGUMENTS` (if any) is a hint/topic for the commit message.

Quick summary of what to do (the skill is authoritative):

1. Check the current branch and `git status --short`. If nothing to commit and
   already in sync, say so and stop.
2. `git add -A`, then commit with an emoji conventional message (single commit by
   default; split only for clearly distinct features). **No AI/tooling
   attribution in commit messages** — see `commit-conventions.md`.
3. Push to `master`: if already on `master`, `git push origin master`. If on a
   working branch, push it, then `checkout master` → `pull --ff-only` → merge the
   branch → `push origin master` → `checkout` back to the working branch.
4. Report the commit subject(s) and the resulting `master` HEAD.

Invoking this command is explicit user direction to commit/push/merge — proceed
without extra confirmation. **Stop and report** on any merge conflict or push
failure; never force-push or rewrite history. Never run a process-killing
command (repo rule).
