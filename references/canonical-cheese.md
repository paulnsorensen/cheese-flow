# Canonical `.cheese` Directories

Most cheese-flow runtime artifacts use a project-root `.cheese/` directory.
For durable knowledge artifacts, "project root" means the canonical main Git
worktree when the current checkout is a linked worktree.

## Active Worktree Root

The active root is the checkout the agent is currently operating in:

```bash
git rev-parse --show-toplevel
```

Use this root for code edits, builds, tests, and branch-local runtime state.

## Canonical Project Root

The canonical project root is used for durable research and spec knowledge that
should survive branch worktrees. Resolve it from the first record in
`git worktree list --porcelain`, falling back to the active root:

```bash
ACTIVE_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
CANONICAL_ROOT="$(
  git -C "$ACTIVE_ROOT" worktree list --porcelain 2>/dev/null \
    | awk 'BEGIN { RS=""; FS="\n" } NR == 1 { sub(/^worktree /, "", $1); print $1 }'
)"
CANONICAL_ROOT="${CANONICAL_ROOT:-$ACTIVE_ROOT}"
```

In Conductor, this prevents research and specs from being stranded in disposable
linked worktree directories.

## Artifact Policy

Write durable knowledge here:

- `<canonical-project-root>/.cheese/research/`
- `<canonical-project-root>/.cheese/specs/`
- `<canonical-project-root>/.cheese/issues/`

Keep branch-local operational reports in the active worktree unless a skill says
otherwise:

- `.cheese/age/`
- `.cheese/cure/`
- `.cheese/cleanup/`

## Gitignored by Design

Both active and canonical `.cheese/` directories are local and gitignored. They
are for agent/user collaboration, not versioned source.

