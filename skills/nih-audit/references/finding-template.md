# Finding block template

Every candidate above the threshold renders one block. The orchestrator
appends every block, sorted by score descending, after the summary table.

```markdown
### Finding #N: <Title> (Score: NN) [AMBIGUOUS if passes diverge >20]

**NIH Code**: `path/to/file.ext:line-line` (N LOC)
**Category**: <CATEGORY>
**Pattern**: <one sentence describing what was detected>

**Recommended Alternative**: `library-name@version`
- Licence: <SPDX id>
- Downloads: N/week | Stars: N | Last commit: YYYY-MM-DD
- Contributors: N
- Type: stdlib | micro-library | framework

**Code Touchpoints**:
- `path:line` — implementation (DELETE or REPLACE)
- `path:line` — import (UPDATE)
- `path:line` — test (UPDATE)

**Effort**: S | M | L (N files, N call sites)

**Migration**:
1. Install: `npm install ...` / `cargo add ...` / `uv pip install ...`
2. Replace: <specific change description>
3. Clean up: <removed files / deleted helpers / pruned tests>

**Scoring**:
- Pass 1: NN  (base NN + evidence NN + context NN)
- Pass 2: NN  (base NN + evidence NN + context NN)
- Final: NN   (average of Pass 1 and Pass 2)

**Why do it**: <maintenance burden removed, upstream bugs already fixed,
stdlib means zero new deps, covers planned spec features, ...>

**Why not**: <trivial code not worth a dep, hot path needing fine control,
intentional design choice documented in spec, transitive deps not wanted,
...>
```

## Required fields

- Score line in the heading.
- NIH Code, Category, Pattern.
- Recommended Alternative with name + version + licence + downloads.
- Effort sizing (S / M / L) with file and call-site counts.
- A 3-step Migration block (Install / Replace / Clean up).
- Both pass scores plus the average.
- Both Why-do-it and Why-not — the human decides; render the trade-off
  honestly.

## When to omit a block

Drop a candidate before rendering if any of:

- The recommended library is already in the project's `depManifest` and
  the candidate just hasn't migrated to it yet — surface as a "use existing
  dep" recommendation instead.
- The category yielded zero passing libraries (all unmaintained, all GPL,
  etc.) — note the category had no good alternatives in the summary, but
  do not render an empty Finding.
