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

The `justfile` loops each dim directory and calls the comparator with two
explicit file arguments:

```bash
python python/tools/age_fixture_diff.py <dim>/actual.json <dim>/expected.json
```

The comparator:
1. Receives `actual.json` (written by the dim agent) and `expected.json`
   (the checked-in fixture).
2. Verifies the `dimension` field matches.
3. Matches observations by `id` first (exact), then falls back to fuzzy
   scoring. Each actual observation is consumed at most once (one-to-one).
4. Exits non-zero if any expected observation is unmatched; prints a
   JSON summary with `misses` for each failure.

---

## Failure modes

**missing id** -- `expected.json` references an observation `id` that is
absent from `actual.json` and no fuzzy match succeeds. Reported in `misses`.

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
