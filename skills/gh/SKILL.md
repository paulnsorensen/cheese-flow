---
name: gh
allowed-tools: bash
description: >
  Complete GitHub tasks using the gh CLI. Use for any GitHub operation —
  PRs, issues, CI checks, repo management, releases, code search.
  Use git commands (log, diff, status) for local context.
  Use when the user says "create PR", "merge PR", "check CI", "list issues", "review PR",
  "PR status", "close issue". Do NOT use for local git operations like
  commit, stage, or push — use commit skill for those. Do NOT use for code quality
  review — use age or code-review. Examples: "review PR 14", "create a PR for my
  branch", "what's the CI status on this PR?", "list open issues labeled bug",
  "merge PR 23 with squash", "show me issue 42 with comments".
---

# gh

GitHub operations via the `gh` CLI and `git` (read-only).

**Rule**: `git` is read-only here — log, diff, status only. No commits, no push via git.

---

## CLI Rules

**Never pipe `gh` output.** Use `--json`, `--jq`, and `--template` flags instead:

```bash
# WRONG — pipe needs external jq
gh pr list --json number | jq '.[].number'

# RIGHT — inline jq
gh pr list --json number --jq '.[].number'

# Complex filtering
gh pr list --json number,title,state --jq '.[] | select(.state == "OPEN") | .title'

# Go template alternative
gh pr view 42 --json title --template '{{.title}}'
```

**Never use heredoc `--body` with `gh pr create`.** Use `--body-file` instead.

---

## Operation Reference

### Pull Requests

| Operation | Command |
|-----------|---------|
| View PR | `gh pr view <number>` |
| PR diff | `gh pr diff <number>` |
| PR checks / CI status | `gh pr checks <number>` |
| List open PRs | `gh pr list --state open` |
| Create PR | `gh pr create --title "..." --body-file <file>` |
| Merge PR | `gh pr merge <number> --squash` |
| Review PR | `gh pr review <number> --approve` / `--request-changes` |
| List review comments | `gh api repos/{owner}/{repo}/pulls/<number>/comments` |

### Issues

| Operation | Command |
|-----------|---------|
| View issue | `gh issue view <number>` |
| List issues | `gh issue list --state open --label bug` |
| Create issue | `gh issue create --title "..." --body "..."` |
| Close issue | `gh issue close <number>` |
| Search issues | `gh search issues "query" --repo owner/repo` |

### CI/CD

| Operation | Command |
|-----------|---------|
| Watch a run | `gh run watch <id>` |
| View failed logs | `gh run view <id> --log-failed` |
| Re-run failed jobs | `gh run rerun <id> --failed` |
| Trigger workflow | `gh workflow run <workflow>` |
| List runs | `gh run list --workflow <name>` |

### Releases

| Operation | Command |
|-----------|---------|
| Create release | `gh release create <tag> --notes "..."` |
| Delete release | `gh release delete <tag>` |
| List releases | `gh release list` |

---

## Git Context (read-only)

Before creating PRs or writing descriptions, use git for local context:

```bash
git log --oneline origin/main..HEAD   # commits going into the PR
git diff origin/main...HEAD           # full diff for PR body
git status                            # working tree state
```

---

## Common Workflows

### Create a PR

```bash
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD

gh pr create --title "Add user authentication" --body-file /tmp/pr-body.md
```

### Review a PR

```bash
gh pr view 42
gh pr diff 42
gh pr checks 42
gh api repos/{owner}/{repo}/pulls/42/comments
```

### Investigate Failed CI

```bash
gh pr checks 42
gh run list --limit 5
gh run view <run-id> --log-failed
```

### Merge a PR

```bash
gh pr merge 42 --squash
```

---

## What This Skill Doesn't Do

- **Commit, push, rebase, or modify local working tree** — use commit skill
- **Code quality review** — use age or code-review skills
- **Search for code symbols** — use cheez-search
- **Read/write local files** — use cheez-read/cheez-write
