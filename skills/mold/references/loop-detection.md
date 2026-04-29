# Loop detection

The `/mold` dialogue can stall in three predictable ways. The agent watches
for them and surfaces an intervention before the user has to.

## Triggers

### Drift

**Definition.** Four consecutive turns without a new entry in
`Decisions`, `Sketches`, or `Validate cycles` blocks of the state file.

**Signal.** The conversation is *moving* but not *converging* — questions
chase questions, options proliferate, no decisions land.

**Action.**

```
We've gone four turns without a new decision, sketch, or validate cycle.
Two ways to break out:
  A. Synthesis turn — I summarize what we have and propose the next concrete
     step.
  B. Pause — save state to scratch and resume later.

Which?
```

### Bored user

**Definition.** Terse responses (`ok`, `meh`, `idk`, `whatever`, single-word
acknowledgements) **two or more turns in a row**.

**Signal.** The user is no longer engaged. Continuing burns trust.

**Action.** Surface the escape hatches explicitly:

```
You sound disengaged. Options:
  A. Switch modes — `explore` (back up) | `shape` (skip to options) |
     `sketch` (lock interfaces now).
  B. Crystallize what we have, even if rough — I'll mark gaps as [TBD].
  C. Pause — bail out, no artifacts.

Or just type the knob you want.
```

### Rabbit hole

**Definition.** Three or more mode transitions in the last five turns AND no
new state-file entries during that window.

**Signal.** The session is thrashing — every mode change is a context switch
that costs more than it produces.

**Action.** Force a synthesis turn before any further mode change:

```
We have transitioned modes three times in the last five turns without
producing a decision, sketch, or validate cycle. Forcing a synthesis turn:

<one paragraph summarizing where we actually are>

From here, the smallest move is <X>. Confirm or redirect.
```

## Detection mechanics

The state file is the source of truth. After every turn the agent:

1. Updates `Mode history`.
2. Increments `drift_counter` if the turn produced no new entry in
   `Decisions`, `Sketches`, or `Validate cycles`.
3. Resets the counter when an entry lands.
4. Compares the user's last 2 messages against the bored-user pattern.
5. Inspects the last five entries of `Mode history` for the rabbit-hole
   condition.

When any trigger fires, the agent **must** surface it before answering the
substantive question that came in. Loop detection always pre-empts
content.

## False positives

Some legitimate sessions look like drift but are not:

- The user is reading along while the agent does a Sketch sweep — turns
  produce sketches, so the counter resets.
- The user is reading a `/briesearch` synthesis — that synthesis writes a
  `Validate cycles` entry, which resets the counter.
- The user is intentionally exploring options without picking one — the
  Shape mode produces an Option block in the state file's `Decisions` (as
  a candidate, marked `[?]`), which still resets the counter.

If the user pushes back on an intervention ("we're fine, keep going"),
record the override and skip the next two trigger checks. Do not let loop
detection itself become noise.
