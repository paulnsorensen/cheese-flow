# Output-Format Dim — Protocol

The output-format reviewer checks the structure of the target's emitted
output: summary-first layout, scannable tables, threshold communication,
detail-vs-summary separation, and structured output for downstream consumers.

## Why this dim exists

Reports that mix summary and detail, or that scatter findings across
prose paragraphs, force the reader to do parser work. Structured output
also lets downstream skills (`/cleanup`, `/fromage cook`) act on
findings without LLM intervention.

## Patterns the dim looks for

### `output-format.no_summary_first`

Detail comes before any one-line assessment. Reader must scroll to
learn the verdict.

```
# Bad
... 80 lines of detail ...
Result: ready to merge.

# Good
**Result: ready to merge** (3 findings, all bucketed as `med`).

... 80 lines of detail ...
```

### `output-format.no_findings_table`

Multiple findings emitted as prose paragraphs instead of a scannable
table. Use a table when there are ≥ 2 findings.

```
| id | category | file:line | narrative | bucket |
|---|---|---|---|---|
| activation-1 | activation.missing_triggers | agents/foo.md.eta:3 | Description has no quoted user phrases. | high |
```

### `output-format.no_threshold_tally`

Agent applies a threshold (e.g., surface only findings at `med` or
`high`) but never declares "N findings below threshold (not shown)".
Reader can't tell whether the agent looked.

```
Surfacing 4 findings (`med` and above).
Below threshold: 7 findings (not shown).
```

### `output-format.detail_to_caller`

Full report dumped into caller's context. Should write to
`$RUN_DIR/<dim>.json` (or a named temp file) and return only a
pointer + summary.

```
Report: $RUN_DIR/skill-improver/<slug>.md
Fixes:  $RUN_DIR/skill-improver/<slug>.fixes.json   (3 entries)
Suggestions: $RUN_DIR/skill-improver/<slug>.suggestions.json (5 entries)
```

### `output-format.unstructured_output`

Output is freeform prose. Downstream consumers can't parse it.
Structured JSON output is required when:

- Findings are intended for `/cleanup` consumption.
- Findings feed into `/fromage cook --suggestions`.
- The output appears in a CI log that needs grepping.

### `output-format.no_clean_run_signal`

Identical-looking output for "0 findings" and "N findings". Reader
can't grep for green. Add a one-line state header:

```
Status: clean (0 findings).
```

### `output-format.no_schema_reference`

Agent emits JSON without linking to a schema doc. Future maintainers
can't verify drift. Reference `skills/age/references/sidecar-schema.md`
for /age-shaped output (which /skill-improver reuses per spec SI-2).

## Layout pattern (summary-first + detail)

```markdown
## Summary

<one-line verdict>

| dim | findings | high | med | low |
|---|---|---|---|---|

## High-stakes findings

### <dim>

<observation block>

## Medium-stakes findings

### <dim>

<observation block>

## Below threshold

<N> findings (not shown).
```

## Stake calibration

| Defect | Default bucket |
|---|---|
| `unstructured_output` on a report-emitting agent | `med` |
| `no_summary_first` | `med` |
| `no_threshold_tally` | `med` |
| `detail_to_caller` (context pollution) | `med` |
| `no_clean_run_signal` | `low` |
| `no_schema_reference` | `low` |

## What this dim does NOT do

- Does not evaluate description routing copy — that's activation.
- Does not evaluate tool reachability — that's tool-scoping.
- Does not evaluate prompt body wording — that's prompt-quality.
