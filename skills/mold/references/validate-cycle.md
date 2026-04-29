# The Validate Cycle

A named cross-mode sub-pattern. Any mode can invoke it when the agent or
the user holds an unverified claim. The cycle forces a stated hypothesis
plus a judgment step, which prevents wishy-washy "let me research this and
come back" patterns.

## Anatomy

1. **State the hypothesis.** Single declarative sentence. Falsifiable. The
   anchor for the rest of the cycle.
2. **Dispatch evidence.** Usually `/briesearch`. Sometimes `cheez-search`
   or `cheez-read` is enough. Sometimes both run in parallel.
3. **Judge.** Three outcomes — **SUPPORTED**, **CONTRADICTED**, **REFINED**.
4. **Settle.** Continue from the mode that invoked the cycle. The mode
   history records the cycle.

## Dialogue script

The agent **announces** the cycle before dispatching. Use this exact shape
so the user knows what is happening and can interrupt:

```
Launching a validate cycle on hypothesis:
  "<single declarative sentence>"

Plan:
  /briesearch  — fetch <focused question>
  Judge        — does the evidence support, contradict, or refine?
  Settle       — accept, revise, or reject. Continue from <current mode>.
```

After the evidence returns, render a one-paragraph judgment plus the
verdict tag:

```
Judgment: <2-3 sentences citing evidence and any caveats>.
Verdict: SUPPORTED | CONTRADICTED | REFINED
```

If REFINED, restate the hypothesis with new precision and either re-validate
or accept the refined form.

## When to invoke

- **Ground** — any user claim about local code or external behaviour the
  agent can verify.
- **Shape** — before recommending Option A over B, validate the load-bearing
  assumption ("Option A is faster" → measure or cite).
- **Sketch** — before locking a signature that mirrors a third-party API,
  fetch and compare.
- **Diagnose** — the existing hypothesis-ranking *is* a Validate Cycle, run
  in parallel for 3-5 hypotheses at once.
- **Grill** — when stress-testing surfaces an unverified assumption, pause
  Grill, run the cycle, return.

## Validate Cycle vs. bare `/briesearch`

A bare `/briesearch` is a research dispatch. The Validate Cycle adds:

- The **stated hypothesis** (commitment to an assertion).
- The **judgment step** (verdict tag, not just a summary).
- The **decision recorded in state** (`Decisions` block on SUPPORTED;
  `[CONFLICT]` marker on CONTRADICTED; restated hypothesis on REFINED).

Direct `/briesearch` calls are allowed but discouraged. The framing matters.

## Cap

Same `/briesearch` budget as the rest of the skill: **max two** calls per
session unless the user requests more. Validate Cycles backed by `cheez-*`
evidence alone are unbudgeted because they only touch local code.

## State recording

Every cycle gets one line in the state file's `Validate cycles` block:

```
- cycle <N>: "<hypothesis>" → SUPPORTED|CONTRADICTED|REFINED (<source> turn <K>)
```

Followed by:

- on SUPPORTED — append the decision to `Decisions` with the same cycle id.
- on CONTRADICTED — append a `[CONFLICT]` line to `Open questions`.
- on REFINED — append the restated hypothesis as a new cycle entry, and
  link the prior id (`refined from cycle <prior>`).

## Confidence impact

The document-level confidence formula in `references/spec.md` adds points
for SUPPORTED cycles and subtracts points for CONTRADICTED ones. Keeping
the state file accurate is what makes the formula honest.
