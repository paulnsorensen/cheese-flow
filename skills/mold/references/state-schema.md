# State file schema

`/mold` keeps one scratch state file per run. The path mirrors `/briesearch`'s
scratch convention so cleanup is predictable.

## Path

```
${TMPDIR:-/tmp}/cheese-flow-mold-<run_id>/state.md
```

Where `<run_id>` is `<YYYYmmdd-HHMMSS>-<slug>`. The slug is derived from the
input (lowercase, drop stopwords, kebab-case, cap at 5 words). The directory
is auto-evicted at the OS's `$TMPDIR` schedule.

## Schema

```markdown
# /mold state — <run_id>
mode: <Explore|Ground|Shape|Sketch|Grill|Diagnose>
input_summary: <one paragraph in the user's words, paraphrased>
drift_counter: <integer>
briesearch_used: <integer>      # 0..2 unless user lifts the cap

## Decisions (resolved)
- <Decision title> — <one-line summary> (agreed turn <N>)
- ...

## Sketches (locked interfaces)
- module: <file or module path within the slice>
  slice: domains/<name> | adapters/<name> | app | domains/common
  signature: |
    def <name>(
        <arg>: <Type>,
        ...
    ) -> <Return>
  responsibilities: [<one>, <two>, <three>]
  seams: [<queue>, <cache>, <event_bus>, ...]
  error_shape: [<ExceptionA>, <ResultVariantB>]

## Validate cycles
- cycle 1: "<hypothesis>" → SUPPORTED (briesearch turn 6)
- cycle 2: "<hypothesis>" → REFINED (cheez-search turn 9; see cycle 3)
- cycle 3: "<refined hypothesis>" → SUPPORTED (cheez-read turn 10)
  refined_from: cycle 2
- cycle 4: "<hypothesis>" → CONTRADICTED (briesearch turn 14)
  conflict_id: cf-1

## Open questions
- [?] <agent uncertainty> — agent recommends <answer>
- [TBD] <user-deferred decision> — user wants to think
- [BLOCKED] <external dependency>
- [CONFLICT cf-1] <statement> contradicted by <evidence>

## Grill turns
- turn <N>: branch=<name> question="<short>" recommendation=<choice> user_answer=<choice>
- ...

## Quality gates
- `<command>` — <what it checks> (agreed turn <N>)
- ...

## Reproduction loop  # Diagnose mode only
technique: <failing-test|curl-script|cli-invocation|headless-browser|replay|throwaway-harness|property-fuzz|bisection|differential|HITL-bash>
command: |
  <exact, deterministic command or script>
failure_signal: <specific symptom>
reproduction_rate: <100% | high | flaky>
steps:
  - <step 1>
  - <step 2>
expected: <what should happen>
actual: <what happens>

## Mode history
Explore (1-3) → Ground (4-5) → Shape (6-8) → [validate cycle 1] → Sketch (9-11)
  → [validate cycle 2] → [validate cycle 3] → Grill (12-now)
```

## Field rules

- **mode** — current mode. Updated on every transition.
- **input_summary** — frozen on entry. Only updated if the user explicitly
  redirects the problem.
- **drift_counter** — integer, see `loop-detection.md`. Reset to 0 on any
  new `Decisions`, `Sketches`, or `Validate cycles` entry.
- **briesearch_used** — incremented when a Validate Cycle dispatches
  `/briesearch`. Capped at 2 by default. Lifted only on explicit user
  request.
- **Decisions** — append-only. Each line is `<title> — <summary> (agreed
  turn <N>)`. Decisions stand until the user explicitly reverses one.
- **Sketches** — append-only. Locked sketches feed the spec verbatim.
  Each sketch is a small block with `module`, `slice`, `signature`,
  `responsibilities`, `seams`, `error_shape`. The `slice` field names the
  Sliced Bread slice (`domains/<name>`, `adapters/<name>`, `app`, or
  `domains/common`) and gates the curdle crust check.
- **Validate cycles** — append-only. Outcomes are exactly one of `SUPPORTED`,
  `CONTRADICTED`, `REFINED`. REFINED cycles point at their refined-form id.
  CONTRADICTED cycles get a `conflict_id` that ties to an `Open questions`
  entry.
- **Open questions** — every entry carries one of `[?]`, `[TBD]`,
  `[BLOCKED]`, `[CONFLICT <id>]`. The Curdle coherence gate fails if
  any entry lacks a marker.
- **Grill turns** — append-only. One line per Grill question. Records the
  branch traversed, the question asked, the agent's recommended answer, and
  the user's chosen answer. Tracks turn-completion (presence), not content
  quality. The coherence checklist's "Chosen option Grilled" item counts
  branches covered against the agent's branch list at Sketch exit.
- **Quality gates** — append-only. Each entry is a runnable command with a
  one-line description. Migrates verbatim into the spec's `Quality Gates`
  section. Empty if the dialogue did not specify gates.
- **Reproduction loop** — populated only when Diagnose ran a Phase 0 loop.
  Migrates verbatim into the spec's `Reproduction` section. Human-supplied;
  the agent does not infer steps or signals.
- **Mode history** — turn-numbered, includes inline cycle markers.

## Lifecycle

- **Create** — on first turn, after routing picks the entry mode.
- **Update** — every turn the agent writes the file (replace, not append).
- **Read** — the agent reads the previous state at the start of each turn.
- **Migrate to spec** — on Curdle, the spec template absorbs
  `Decisions`, `Sketches`, `Quality gates`, and (if Diagnose ran) `Reproduction
  loop` verbatim into named sections. Validate cycles feed confidence and the
  spec's evidence rows. `Grill turns` is not migrated — it serves the
  coherence checklist and stays in scratch state.
- **Cleanup** — after a successful Curdle *and* the user accepts the
  hand-off offer, the run directory is removed. Otherwise it stays for the
  OS to evict.

