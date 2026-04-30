# Fixture Protocol

L2 quality gate for `/age`. One fixture per dim under `tests/age-fixtures/<dim>/`.
Runnable via `just test-age-fixtures`.

---

## Directory layout

```
tests/age-fixtures/
  <dim>/
    diff.patch      -- real-file-shaped unified diff (input to the dim agent)
    expected.json   -- subset of the per-agent return contract
```

One directory per dim: `correctness`, `security`, `complexity`, `encapsulation`,
`spec`, `precedent`, `deslop`, `assertions`.

---

## `expected.json` schema

A subset of the per-agent return contract (`sidecar-schema.md`). Only fields
used by the comparator need to be present:

```json
{
  "dimension": "<dim>",
  "observations": [
    {
      "id": "<dim>-1",
      "bucket": "high",
      "narrative": "...",
      "anchor": {"start": "42:a3f"}
    }
  ]
}
```

Required fields per observation: `id`, `bucket`, `narrative`, `anchor.start`.
All other fields (`evidence`, `consideration`, `fix`, etc.) are optional in
`expected.json` and ignored by the comparator.

---

## Comparison tolerances

`python/tools/age_fixture_diff.py` enforces:

| Field | Rule |
|---|---|
| `dimension` | Exact match |
| `bucket` | Exact match (`low`, `med`, or `high`) |
| `narrative` | Levenshtein ratio >= 0.6 via `difflib.SequenceMatcher` |
| `anchor.start` (line number) | Within +/- 1 of expected (hash ignored) |

Any observation failing one of these four rules fails the L2 gate.
Other fields are informational only; their mismatches are logged but do not
fail the gate.

---

## How `just test-age-fixtures` works

```justfile
test-age-fixtures:
    python python/tools/age_fixture_diff.py tests/age-fixtures/
```

The comparator:
1. Scans `tests/age-fixtures/` for `<dim>/` subdirectories.
2. For each dim, reads `expected.json` and locates `actual.json` (written by
   the dim agent during the test run).
3. Compares per the tolerances above.
4. Exits non-zero if any observation fails; prints a diff for each failure.

---

## Failure modes

**orphan match** -- `expected.json` references an observation id that has no
counterpart in `actual.json`. Fail with: `orphan: <id> not found in actual`.

**missing actual.json** -- the dim agent did not write output. Fail with:
`missing: tests/age-fixtures/<dim>/actual.json`.

**bucket mismatch** -- actual bucket differs from expected. Exact match
required; no fuzzy logic.

**narrative drift** -- Levenshtein ratio below 0.6. Printed as:
`narrative ratio <actual_ratio> < 0.60 for <id>`. Update `expected.json`
when the narrative intentionally changes.

---

## Adding a new fixture

1. Add a new directory: `tests/age-fixtures/<new-dim>/`.
2. Add `diff.patch`: a real-file-shaped unified diff that exercises the dim's
   rubric. Use an actual file from the repo, not synthetic content.
3. Run the dim agent against the patch to generate `actual.json`.
4. Copy `actual.json` to `expected.json` and trim to only the fields required
   by the comparator schema above.
5. Run `just test-age-fixtures` to confirm the fixture passes baseline.
6. Commit both `diff.patch` and `expected.json`.

New dims require a fixture before merging (D-19).
