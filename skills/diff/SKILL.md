---
name: diff
model: haiku
context: fork
allowed-tools: Bash, mcp__tilth__tilth_search, mcp__tilth__tilth_read
description: >
  Token-frugal pre-commit smoke test of staged or unstaged changes. Scans for
  blockers (secrets, debug statements, commented code, silent failures) and
  warnings (oversized functions/files, deep nesting, domain leakage). Forks
  into its own context, returns a compact bulleted report. Use when asked to
  review staged changes, run a pre-commit check, or when /diff is invoked.
---

# diff

Quick smoke test. Catch the obvious, skip the nitpicks. Optimised for tokens.

## Protocol

### 1. Scope the diff (cheap)

Run, in this order, stopping at the first that returns content:

```bash
git diff --cached --name-only            # staged paths
git diff --name-only                     # unstaged paths
git diff --name-only {ref}               # vs explicit ref
```

Then capture stats only — never dump the full patch into context:

```bash
git diff --numstat <scope>               # path<TAB>+<TAB>-
```

If empty: reply `No changes.` and stop.

### 2. Pull diff hunks for changed files only

For each changed path, fetch only the patch hunks (not full files):

```bash
git diff --unified=2 -- <path>
```

Process inline. Skip files marked binary in `--numstat` (`-\t-\t<path>`). Drop
lockfiles (`*.lock`, `package-lock.json`) — flag their presence as a single
warning rather than scanning. Combined hunk budget: 400 lines; truncate
noisily beyond.

If a finding's context truly requires the surrounding code, fetch a single
section with `mcp__tilth__tilth_read` (`section: "<start>-<end>"`). Never read
whole files.

### 3. Scan for red flags

Use `mcp__tilth__tilth_search` with `kind: "content"` and a `glob:` filter
scoped to changed paths for cheap pattern checks. Use the captured diff
hunks for line-anchored evidence.

Only inspect added lines (`^+` and not `^+++`). Check these categories in
priority order.

**Blockers (must fix before commit):**

- Hardcoded secrets, API keys, tokens, passwords (look for `AKIA[0-9A-Z]{16}`, `sk-[a-zA-Z0-9]{32,}`, `-----BEGIN .* PRIVATE KEY-----`, hex strings ≥ 32 chars near `key|token|secret|password`)
- Debug statements left in (`console.log`, `dbg!`, `print(`, `fmt.Println`, `pp.pp`)
- Commented-out code blocks (≥ 3 contiguous comment lines that parse as code)
- TODO/FIXME/HACK without ticket reference
- Empty catch/except blocks
- New I/O (`fs.`, `fetch(`, `requests.`, DB calls) with no error handling on the new path

**Warnings (worth a second look):**

- New dependencies in `package.json` / `Cargo.toml` / `pyproject.toml` / `go.mod`
- Functions exceeding 40 lines (use `tilth_search` for the symbol, check span)
- Files exceeding 300 lines (`git diff --numstat` final line count vs head)
- Nesting deeper than 3 levels (visual scan of the hunk indentation)
- Core model/domain files importing infrastructure (grep new `import` lines)

### 4. Report (compact)

**Clean case** — single line:

```
clean — {N} files, +{adds}/-{dels}
```

**Issues found** — bulleted, no prose, no preamble:

```
{N} files, +{adds}/-{dels}.

Blockers:
- {path}:{line} {category} — {evidence ≤ 80 chars}

Warnings:
- {path}:{line} {category} — {evidence ≤ 80 chars}
```

Omit any section with zero entries. Do not echo the diff. Do not narrate the scan.

### 5. Do NOT

- Quote diff hunks back to the caller
- Suggest refactoring or style fixes
- Flag patterns consistent with the rest of the codebase
- Recommend architectural changes
- Add docstrings or comments
- Run tests (separate step)
- Re-read files you've already inspected

For thorough review, defer to `/age` or `/code-review`.

## Token discipline

- Forked subagent context — caller never sees the raw diff.
- Patch hunks live in this context only; the report is the only thing returned.
- Hard cap on report: 40 lines (≈1500 tokens). If findings exceed it, surface
  top-10 blockers + top-5 warnings, append `+{remaining} more (see git diff)`.
- Each finding is one line: `path:line CATEGORY — ≤80-char evidence`. No prose
  between bullets, no quoting hunks, no explanatory headers beyond `Blockers:`
  / `Warnings:`.
- Never fetch external docs — escalate to `/briesearch` if needed.

## Gotchas

- Haiku may miss base64-encoded secrets and hex tokens without common prefixes — surface anything suspicious as a warning rather than dropping it.
- `tilth_search` operates on the working tree, not the diff; cross-reference line numbers against the hunk before reporting.
- Use `--no-pager` on every git invocation to avoid pager noise.
