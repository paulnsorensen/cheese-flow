# Fixture Protocol

L2 quality gate for `/skill-improver`. One fixture per dim under
`tests/skill-improver-fixtures/<dim>/`. Runnable via
`just test-skill-improver-fixtures`.

The protocol mirrors `skills/age/references/fixture-protocol.md` but the
input is a target file rather than a diff (per spec FR-1, SI-5).

---

## Directory layout

```
tests/skill-improver-fixtures/
  <dim>/
    target.md.eta   -- seeded agent or skill definition with one
                       deliberate defect that the dim's rubric should
                       catch. Real-shape file, not synthetic stub.
    expected.json   -- subset of the per-agent return contract
```

One directory per dim: `activation`, `tool-scoping`, `context`,
`prompt-quality`, `output-format`.

---

## `expected.json` schema

A subset of the per-agent return contract (`skills/age/references/sidecar-schema.md`).
Only fields used by the comparator need to be present:

```json
{
  "dimension": "<dim>",
  "observations": [
    {
      "id": "<dim>-1",
      "bucket": "high",
      "narrative": "...",
      "anchor": {"start": "3:000"}
    }
  ]
}
```

Required fields per observation: `id`, `bucket`, `narrative`,
`anchor.start`. All other fields (`evidence`, `consideration`, `fix`,
etc.) are optional in `expected.json` and ignored by the comparator.

Hash digits are placeholders (`000`); the comparator only uses the line
number prefix and ignores the hash component (per `age_fixture_diff.py`
tolerances).

---

## Comparison tolerances (reused from /age)

`python/tools/age_fixture_diff.py` (no fork, no copy) enforces:

| Field | Rule |
|---|---|
| `dimension` | Exact match |
| `bucket` | Exact match (`low`, `med`, or `high`) |
| `narrative` | Levenshtein ratio ≥ 0.6 via `difflib.SequenceMatcher` |
| `anchor.start` (line number) | Within ±1 of expected (hash ignored) |

Any observation failing one of the four rules fails the L2 gate. Other
fields are informational only.

---

## How `just test-skill-improver-fixtures` works

The justfile loops each dim directory and calls the comparator with two
explicit file arguments:

```bash
python python/tools/age_fixture_diff.py <dim>/actual.json <dim>/expected.json
```

The comparator:

1. Receives `actual.json` (written by the dim agent during a real
   `/skill-improver` run against `target.md.eta`) and `expected.json`
   (the checked-in fixture).
2. Verifies the `dimension` field matches.
3. Matches observations by `id` first (exact), then falls back to fuzzy
   scoring. Each actual observation is consumed at most once.
4. Exits non-zero if any expected observation is unmatched; prints a
   JSON summary with `misses` for each failure.

The recipe expects `actual.json` to be present per dim. Run the dim
agent against the seeded target to populate it before invoking the
gate (mirrors `/age`'s flow).

---

## Adding a fixture

1. Create `tests/skill-improver-fixtures/<dim>/target.md.eta` — a real
   agent or skill definition with **one deliberate defect** the dim's
   rubric should catch.
2. Run `/skill-improver tests/skill-improver-fixtures/<dim>/target.md.eta`
   to generate the dim's `actual.json`.
3. Copy `actual.json` to `expected.json` and trim to only the fields
   required by the comparator schema above.
4. Run `just test-skill-improver-fixtures` and confirm the fixture
   passes baseline.
5. Commit both `target.md.eta` and `expected.json`.

The seeded defect must be specific to the dim under test — e.g., a
`activation` fixture has a description-as-summary defect, not a
tool-scoping one. Cross-dim fixtures dilute the L2 signal.

---

## Failure modes

**missing id** — `expected.json` references an observation `id` that is
absent from `actual.json` and no fuzzy match succeeds. Reported in
`misses`.

**missing actual.json** — the dim agent did not write output. Fail with:
`missing actual.json (run /skill-improver first to populate)`.

**bucket mismatch** — actual bucket differs from expected. Exact match
required.

**narrative drift** — Levenshtein ratio below 0.6. Update
`expected.json` when the narrative intentionally changes.
