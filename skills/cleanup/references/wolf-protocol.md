# Wolf Protocol

Wolf is the cleaner of last resort in the `/cleanup` path (named after the
fixer in Pulp Fiction). It is the ONLY LLM agent in the cleanup skill.
Wolf fires exactly when `tilth_edit` returns a hash mismatch for a fix entry.

---

## When Wolf fires

The cleanup skill applies each fix mechanically via `tilth_edit`. If the anchor
hash no longer matches the current file state, the skill cannot apply without
human judgment. That is the only trigger for Wolf.

Wolf does NOT fire on: missing files, permission errors, schema validation
failures. Those are hard errors -- fail fast and surface to the caller.

---

## Inputs

Wolf receives exactly three inputs:

1. **`fix`** -- the original fix entry from `<slug>.fixes.json`:
   `{id, dimension, file, anchor: {start, end}, content, rationale, category}`
2. **`current_file_state`** -- the full current content of `fix.file`, read
   via `cheez-read` immediately before Wolf is spawned.
3. **`original_narrative`** -- the observation narrative from the dim agent
   that produced the fix (used as the search signal).

---

## Re-anchor algorithm

1. **Extract tier-1 tokens** from `original_narrative`: function name, class
   name, or type name if present. These are the most stable identifiers.
2. **cheez-search** for the original block using the tier-1 token as query,
   scoped to `fix.file`.
3. **Evaluate matches**:
   - If exactly one match is found at a plausible location, re-anchor:
     set `new_anchor.start` and `new_anchor.end` to the match's line:hash
     values from `cheez-search` output.
   - If zero or multiple matches are found, return skip with reason.
4. **Apply** via `tilth_edit` using the new anchor.
5. **Return** the result object (see Output below).

Wolf MUST NOT make semantic changes. The `content` field is applied verbatim.
Re-anchoring only; the replacement content is unchanged from the original fix.

---

## Output

On success:
```json
{"applied": true, "new_anchor": {"start": "<line:hash>", "end": "<line:hash>"}}
```

On skip:
```json
{"skipped": "<reason>"}
```

Reasons for skip: `"no_match"`, `"ambiguous_match: N candidates"`,
`"narrative_too_generic"`.

Wolf returns one of these two shapes and nothing else. No partial applies,
no semantic rewrites, no suggestions.

---

## What Wolf defers (v1 non-goals)

- Multi-anchor merge (applying when the block was split across lines)
- Semantic auto-fix (rewriting content to match new context)
- Cross-file re-anchor (the fix moved to a different file)

If any of these are needed, Wolf skips with reason and the cleanup report
records it as `wolf_skipped`. The user decides next steps.
