# tilth MCP Reference

tilth is a code intelligence MCP server that replaces grep, cat, find, and ls with AST-aware equivalents. It uses Tree-sitter for structural code parsing and understanding.

## Installation

```bash
# Install CLI
cargo install tilth
# or
npx tilth

# Install MCP server for Claude Code
tilth install claude-code

# With edit mode (hash-anchored editing)
tilth install claude-code --edit
```

## Core Principle: Search First

To explore code, always search first. `tilth_search` finds definitions, usages, and file locations in one call. Use `tilth_files` only for listing directory contents when you have no symbol or text to search for.

## MCP Tools

### tilth_search — Symbol and Content Search

Replaces grep/rg for all code search. Finds where symbols are **defined** — not just where strings appear.

```
tilth_search(query: "handleAuth", scope: "src/")
```

**Parameters:**
- `query` (required): Symbol name, comma-separated symbols, text string, or regex
- `scope`: Directory to search in (default: cwd)
- `kind`: `"symbol"` (default), `"content"`, `"regex"`, or `"callers"`
- `expand`: Number of matches to show full source (default: 2)
- `context`: Path to file being edited — boosts nearby results
- `glob`: File pattern filter — `"*.rs"`, `"!*.test.ts"`, `"*.{go,rs}"`

**Output per match:**
```
## <path>:<start>-<end> [definition|usage|impl]
<outline context>
<expanded source block>
── calls ──
<name>  <path>:<start>-<end>  <signature>
```

**Multi-symbol search:**
```
tilth_search(query: "ServeHTTP, HandlersChain, Next", scope: ".")
```

**Callers query:**
```
tilth_search(query: "validateToken", kind: "callers", scope: ".")
```

**Content search (literal text):**
```
tilth_search(query: "TODO: fix", kind: "content", scope: ".")
```

**Regex search:**
```
tilth_search(query: "rate.?limit", kind: "regex", scope: ".")
tilth_search(query: "FIXME\\(.*?\\):", kind: "regex", scope: "src/")
```
Pass the bare regex — do not wrap in `/.../` delimiters.

### tilth_read — Smart File Reading

Replaces cat/head/tail. Small files → full content. Large files → structural outline.

```
tilth_read(path: "src/auth.ts")
tilth_read(path: "src/auth.ts", section: "44-89")
tilth_read(path: "docs/guide.md", section: "## Installation")
tilth_read(paths: ["src/auth.ts", "src/routes.ts"])
```

**Output:**
```
# Full/section mode
<line_number>:<hash>│ <content>

# Outline mode (large files)
[<start>-<end>]  <symbol name>
```

**Hash anchors** are used for editing with `tilth_edit`. The format is `<line>:<hash>│ <content>`.

### tilth_files — File Finding

Replaces find, ls, pwd, and the host Glob tool.

```
tilth_files(glob: "**/*.ts", scope: "src/")
```

**Output:**
```
<path>  (~<token_count> tokens)
```

### tilth_deps — Dependency Graph

Shows what imports a file and what it imports. Use ONLY before renaming, removing, or changing an export's signature.

```
tilth_deps(path: "src/auth.ts")
```

**Output:**
```
── imports ──
  express        external
  @/config       src/config/index.ts

── imported by ──
  src/routes/api.ts:5
  src/middleware/auth.ts:3
```

### tilth_edit — Hash-Anchored Editing

Uses hash anchors from `tilth_read` for precise edits. Replaces the host Edit tool.

**Single line edit:**
```json
tilth_edit({
  "path": "src/auth.ts",
  "edits": [
    { "start": "42:a3f", "content": "  let x = recompute();" }
  ]
})
```

**Multi-line range replacement:**
```json
tilth_edit({
  "path": "src/auth.ts",
  "edits": [{
    "start": "44:b2c",
    "end": "89:e1d",
    "content": "export function handleAuth(req, res, next) {\n  // new implementation\n}"
  }]
})
```

**Delete a block:**
```json
tilth_edit({
  "path": "src/auth.ts",
  "edits": [
    { "start": "44:b2c", "end": "89:e1d", "content": "" }
  ]
})
```

**Show diff:**
```json
tilth_edit({
  "path": "src/auth.ts",
  "diff": true,
  "edits": [...]
})
```

**Hash mismatch** → file changed since read, re-read and retry.

After editing a function signature, `tilth_edit` shows callers that may need updating.

## Session Features

### Session Deduplication

In MCP mode, previously expanded definitions show `[shown earlier]` instead of the full body on subsequent searches. Saves tokens when revisiting symbols.

### Token Budgeting

- Files under ~6000 tokens show in full
- Files over ~6000 tokens get structural outlines
- Use `section` to get hashlined content for specific ranges

## Supported Languages

Tree-sitter parsing for: Rust, TypeScript, TSX, JavaScript, Python, Go, Java, Scala, C, C++, Ruby, PHP, C#, Swift

## DO NOT Rules

- DO NOT use Read if content is already shown in expanded search results
- DO NOT use Grep, Read, or Glob — use tilth equivalents instead
- DO NOT re-read files already shown earlier in the session
- DO NOT use host Edit tool — use tilth_edit exclusively

## Best Practices

1. **Search first** — `tilth_search` finds definitions and usages together
2. **Read smart** — let tilth decide full vs outline based on file size
3. **Memorize anchors** — note hash anchors from reads for later edits
4. **Check deps** — use `tilth_deps` before major refactoring
5. **Follow calls** — expanded results include callees for tracing

## CLI Usage (reference)

```bash
tilth <path>                      # read file (outline if large)
tilth <path> --section 45-89      # exact line range
tilth <path> --section "## Foo"   # markdown heading
tilth <path> --full               # force full content
tilth <symbol> --scope <dir>      # definitions + usages
tilth "TODO: fix" --scope <dir>   # content search
tilth "/<regex>/" --scope <dir>   # regex search
tilth "*.test.ts" --scope <dir>   # glob files
tilth diff HEAD~1                 # structural diff (function-level)
tilth --map --scope <dir>         # codebase skeleton (CLI only)
```

Note: `--map` is available in CLI but not as MCP tool — benchmarks showed AI agents overused it.
