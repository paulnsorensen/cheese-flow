# Sidecar schema

The contract every `/age` dim agent emits and every downstream consumer
(`/cleanup`, `/fromage cook`, `age_fixture_diff.py`) reads.

Three artifacts are defined here:

1. **Per-agent return contract** — one `<dim>.json` per dim, emitted into
   `$RUN_DIR` by every dim agent.
2. **`<slug>.fixes.json`** — sidecar of mechanically-applicable fixes,
   consumed by `/cleanup`.
3. **`<slug>.suggestions.json`** — sidecar of narrative-shaped guidance,
   consumed by `/fromage cook`.

## Anchor format

All anchors are tilth `line:hash` strings — `"<line>:<hash>"` where the
hash is FNV-1a 12-bit over the source line content. Example: `"42:a3f"`.

`tilth_edit` validates these natively. A hash mismatch on apply means the
file moved underneath the anchor — the cleanup skill routes to its
`cleanup-wolf` sub-agent.

## Per-agent return contract

Every dim agent writes exactly one file:

```
$RUN_DIR/<dim>.json
```

Shape:

```json
{
  "dimension": "<dim>",
  "summary": "1-2 sentences",
  "stake": "<high|medium|advisory>",
  "scope_match": true,
  "observations": [
    {
      "id": "<dim>-1",
      "file": "src/foo.ts",
      "anchor": {"start": "42:a3f", "end": "45:b1c"},
      "bucket": "high",
      "narrative": "...",
      "evidence": [
        "src/foo.ts:42 imports from src/bar/internal/baz.ts"
      ],
      "consideration": "Going through bar/index.ts requires bar to expose `frob()`",
      "fix": {
        "category": "deslop.swallowed_catch",
        "content": "try { ... } catch (e) { logger.error(e); throw }"
      }
    }
  ],
  "manual_review_concerns": [
    {
      "topic": "data-flow",
      "summary": "...",
      "files": ["src/auth.ts:12"]
    }
  ]
}
```

### Field rules

- **`dimension`** — must match the dim name (`correctness`, `security`,
  `complexity`, `encapsulation`, `spec`, `precedent`, `deslop`,
  `assertions`).
- **`stake`** — fixed per dim. Do not vary at runtime.
  - high: `correctness`, `security`, `encapsulation`, `spec`
  - medium: `complexity`, `deslop`, `assertions`
  - advisory: `precedent`
- **`scope_match`** — `false` when the dim's rubric does not apply to
  this diff. Pair with `observations: []`.
- **`bucket`** — exactly one of `low | med | high`. **No numeric scores
  anywhere.**
- **`narrative`** comes BEFORE the bucket value in any rendered report
  (Greptile severity-at-end pattern). The agent need not enforce render
  order; it just emits the field.
- **`evidence`** — at least one entry per observation. Each entry is a
  verifiable fact: `file:line`, prior commit sha, output of a tool, etc.
  An observation without evidence is a verdict, not amplification.
- **`consideration`** — narrative-shaped guidance; required when `fix`
  is unset.
- **`fix`** — set ONLY when all three hold:
  1. Hash-anchored (the `anchor` field is filled with valid `line:hash`
     strings).
  2. Syntactically narrow (replaces a contiguous block; no whole-file
     rewrites).
  3. Complete `content` (the replacement is ready to apply verbatim;
     no `...` placeholders).

  Otherwise leave `fix` unset and write a `consideration`.
- **`manual_review_concerns`** — for shapes the dim cannot adjudicate
  but the reviewer should examine (e.g. taint, data-flow). Surfaced as
  `manual_review_concerns`, not as observations with verdicts.

## `<slug>.fixes.json`

Written by the orchestrator after Phase 3 synthesis. Consumed by
`/cleanup`. Entries are direct `tilth_edit` calls:

```json
{
  "schema_version": 1,
  "ref": "HEAD~3..HEAD",
  "fixes": [
    {
      "id": "deslop-1",
      "dimension": "deslop",
      "operation": "tilth_edit",
      "file": "src/bar.ts",
      "anchor": {"start": "88:b2c", "end": "90:e1d"},
      "content": "...",
      "rationale": "Silent failure pattern (deslop.swallowed_catch)",
      "category": "deslop.swallowed_catch"
    }
  ]
}
```

### Rules

- `operation` is always `"tilth_edit"`. The enum is closed and singular;
  do not add alternatives without revising this schema.
- `id` matches the originating observation's `id`.
- `anchor` and `content` map 1:1 to `tilth_edit`'s `start`, `end`,
  `content` arguments. The cleanup skill calls `tilth_edit` with no
  translation layer.
- A fix entry is invalid if any of `id`, `dimension`, `file`, `anchor`,
  `content`, `rationale`, `category` are missing.

## `<slug>.suggestions.json`

Written by the orchestrator after Phase 3. Consumed by `/fromage cook`
when the user asks it to act on judgment-shaped guidance:

```json
{
  "schema_version": 1,
  "ref": "HEAD~3..HEAD",
  "suggestions": [
    {
      "id": "encap-1",
      "dimension": "encapsulation",
      "file": "src/foo.ts",
      "outline_ref": "44-89",
      "narrative": "Cross-slice import bypasses index",
      "agent_brief_for_cook": "Re-route src/foo.ts:42 through src/bar/index.ts."
    }
  ]
}
```

### Rules

- `outline_ref` is a line range, not a hash anchor. Suggestions are not
  mechanically-applicable.
- `agent_brief_for_cook` is a one-sentence imperative an LLM agent can
  act on. Keep it concrete and bounded.
- `narrative` repeats the originating observation's narrative (so the
  consumer doesn't need to load the dim's full report).

## Validation

`age_fixture_diff.py` validates `<dim>.json` outputs against per-fixture
`expected.json` files using:

- **`dimension`** — exact match required.
- **`bucket`** — exact match required.
- **`narrative`** — Levenshtein similarity ≥ 0.6.
- **`anchor.start`** — line number within ±1 of expected (hash ignored
  for fixture comparison; hash drift across edits is normal).

Any other field comparison is informational only; failures on the four
above fail the L2 gate.
