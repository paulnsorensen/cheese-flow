---
name: gh
model: haiku
context: fork
allowed-tools: mcp__plugin_github_github__*, Bash(git:*), Bash(gh:*)
description: >
  Complete GitHub tasks using the GitHub MCP plugin. Use for any GitHub operation —
  PRs, issues, CI checks, repo management, releases, code search.
  Use git commands (log, diff, status) for local context.
  Prefer MCP tools over gh CLI — they bypass sandbox/TLS issues.
  Use when the user says "create PR", "merge PR", "check CI", "list issues", "review PR",
  "PR status", "close issue". Do NOT use for local git operations like
  commit, stage, or push — use commit skill for those. Do NOT use for code quality
  review — use age or code-review.
examples:
  - "review PR 14"
  - "create a PR for my branch"
  - "what's the CI status on this PR?"
  - "list open issues labeled bug"
  - "merge PR 23 with squash"
  - "show me issue 42 with comments"
---

# gh

GitHub operations via **GitHub MCP plugin** (`mcp__plugin_github_github__*`). MCP is the
default — it works reliably in sandbox with no TLS issues.

**Default**: GitHub MCP tools for all supported operations.
**Fallback**: `gh` CLI only for operations MCP doesn't cover (see table below).
**Rule**: `git` is read-only here — log, diff, status. No commits, no push via git.

---

## MCP Tool Reference

For the full MCP tool catalog (PRs, issues, repos, releases, Copilot), these are the
key tools for common operations:

### Pull Requests

| Operation | MCP Tool |
|-----------|----------|
| Get PR details | `pull_request_read(method: "get", owner, repo, pullNumber)` |
| Get PR diff | `pull_request_read(method: "get_diff", owner, repo, pullNumber)` |
| Get PR files | `pull_request_read(method: "get_files", owner, repo, pullNumber)` |
| Get PR status | `pull_request_read(method: "get_status", owner, repo, pullNumber)` |
| Get PR reviews | `pull_request_read(method: "get_reviews", owner, repo, pullNumber)` |
| Get review comments | `pull_request_read(method: "get_review_comments", owner, repo, pullNumber)` |
| Get PR comments | `pull_request_read(method: "get_comments", owner, repo, pullNumber)` |
| Get check runs | `pull_request_read(method: "get_check_runs", owner, repo, pullNumber)` |
| List PRs | `list_pull_requests(owner, repo, state: "open")` |
| Search PRs | `search_pull_requests(query, owner, repo)` |
| Create PR | `create_pull_request(owner, repo, title, body, head, base)` |
| Merge PR | `merge_pull_request(owner, repo, pullNumber, mergeMethod)` |
| Reply to comment | `add_reply_to_pull_request_comment(owner, repo, pullNumber, commentId, body)` |

### Issues

| Operation | MCP Tool |
|-----------|----------|
| Get issue | `issue_read(method: "get", owner, repo, issue_number)` |
| Get issue comments | `issue_read(method: "get_comments", owner, repo, issue_number)` |
| Get issue labels | `issue_read(method: "get_labels", owner, repo, issue_number)` |
| List issues | `list_issues(owner, repo, state: "OPEN")` |
| Search issues | `search_issues(query, owner, repo)` |

### Code & Repository

| Operation | MCP Tool |
|-----------|----------|
| Get file contents | `get_file_contents(owner, repo, path, ref)` |
| Get commit | `get_commit(owner, repo, sha)` |
| List commits | `list_commits(owner, repo, sha, author, path)` |
| Search code | `search_code(query)` |
| List branches | `list_branches(owner, repo)` |
| List releases | `list_releases(owner, repo)` |
| Get latest release | `get_latest_release(owner, repo)` |

### CI/CD

| Operation | MCP Tool |
|-----------|----------|
| List workflows | `actions_list(method: "list_workflows", owner, repo)` |
| List workflow runs | `actions_list(method: "list_workflow_runs", owner, repo, resource_id)` |
| List workflow jobs | `actions_list(method: "list_workflow_jobs", owner, repo, resource_id)` |
| Get workflow | `actions_get(method: "get_workflow", owner, repo, resource_id)` |
| Get workflow run | `actions_get(method: "get_workflow_run", owner, repo, resource_id)` |
| Get job logs | `get_job_logs(owner, repo, job_id)` |

---

## CLI Rules

**Never pipe `gh` output.** The `gh` CLI has `--json`, `--jq`, and `--template` flags built in:

```bash
# WRONG — pipe triggers compound command detection + needs jq binary
gh pr list --json number | jq '.[].number'

# RIGHT — inline jq, no pipe, embedded interpreter
gh pr list --json number --jq '.[].number'

# Complex filtering
gh pr list --json number,title,state --jq '.[] | select(.state == "OPEN") | .title'

# Go template alternative
gh pr view 42 --json title --template '{{.title}}'
```

**Never use heredoc `--body` with `gh pr create`.** Use MCP or `--body-file` instead.

**Prefer MCP over `gh api`.** Raw API calls can hit TLS issues in sandboxed environments.

---

## CLI Fallback (only when MCP can't do it)

These operations have no MCP equivalent — use `gh` CLI:

| Operation | Command |
|-----------|---------|
| PR diff (formatted) | `gh pr diff <number>` |
| PR checks / CI status | `gh pr checks <number>` |
| Run logs (failed) | `gh run view <id> --log-failed` |
| Watch a run | `gh run watch <id>` |
| Trigger workflow | `gh workflow run <workflow>` |
| Create release | `gh release create <tag>` |
| Delete release | `gh release delete <tag>` |
| Re-run failed CI | `gh run rerun <id> --failed` |

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

```
# Get local context
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD

# Create via MCP
create_pull_request(
  owner: "org",
  repo: "repo",
  title: "Add user authentication",
  body: "## Summary\n...",
  head: "feature-branch",
  base: "main"
)
```

### Review a PR

```
# Get PR details
pull_request_read(method: "get", owner: "org", repo: "repo", pullNumber: 42)

# Get the diff
pull_request_read(method: "get_diff", owner: "org", repo: "repo", pullNumber: 42)

# Get review comments
pull_request_read(method: "get_review_comments", owner: "org", repo: "repo", pullNumber: 42)

# Check CI status
pull_request_read(method: "get_check_runs", owner: "org", repo: "repo", pullNumber: 42)
```

### Check CI Status

```
# Via MCP
pull_request_read(method: "get_check_runs", owner: "org", repo: "repo", pullNumber: 42)

# Or via CLI for more detail
gh pr checks 42
```

### Investigate Failed CI

```
# List workflow jobs
actions_list(method: "list_workflow_jobs", owner: "org", repo: "repo", resource_id: "<run_id>")

# Get logs for failed job
get_job_logs(owner: "org", repo: "repo", job_id: 12345, failed_only: true, return_content: true)
```

### Merge a PR

```
merge_pull_request(
  owner: "org",
  repo: "repo",
  pullNumber: 42,
  mergeMethod: "squash"  # or "merge", "rebase"
)
```

---

## What This Skill Doesn't Do

- **Commit, push, rebase, or modify local working tree** — use commit skill
- **Code quality review** — use age or code-review skills
- **Search for code symbols** — use cheez-search
- **Read/write local files** — use cheez-read/cheez-write
