# Diagnose mode — disciplined symptom triage

Diagnose is the entry mode for stack traces, "X is broken", "Y is slow",
flake reports, and other symptom-shaped inputs. `/mold` Diagnose is
**diagnostic-only**: it shapes the bug and the fix into a spec (plus
optional follow-up issues), then hands off to `/cook` for the actual
patch.

The single most important thing Diagnose does is force agreement on a
**feedback loop** before hypothesising. A fast, deterministic pass/fail
signal is what makes every later step mechanical.

## Phase 0 — Build a Loop (the discipline)

Before generating hypotheses, the agent and user pick **one** feedback
loop technique. The chosen loop is recorded in the state file and becomes
the bug-shaped spec's Reproduction block.

### Menu (try in roughly this order)

| Technique | When to use | Loop output |
| --- | --- | --- |
| Failing test | a unit / integration / e2e seam reaches the bug | red-green at a known seam |
| Curl / HTTP script | bug reproduces against a running dev server | status code + body diff |
| CLI invocation | command-line tool with a fixture input | stdout diff vs known-good snapshot |
| Headless browser | UI-only bug | DOM / console / network assertions |
| Replay captured trace | bug came from a real production payload | replay through code path in isolation |
| Throwaway harness | system is too tangled to test through | minimal subset exercising the bug code path |
| Property / fuzz loop | "sometimes wrong output" with random inputs | failure mode across N inputs |
| Bisection harness | bug appeared between two known states | `git bisect run`-able pass/fail |
| Differential loop | regression between two configs / versions | diff of outputs |
| HITL bash script | last resort, human must click | structured loop driving a human, captured output |

### Iterating on the loop

Once a loop exists, it becomes a product the agent can refine:

- **Faster?** Cache setup, skip unrelated init, narrow the test scope.
- **Sharper signal?** Assert the specific symptom, not "didn't crash".
- **More deterministic?** Pin time, seed RNG, isolate filesystem, freeze
  network.

A 30-second flaky loop is barely better than no loop. A 2-second
deterministic loop is a debugging superpower.

### Non-deterministic bugs

The goal is not a clean repro but a **higher reproduction rate**. Loop the
trigger 100×, parallelise, add stress, narrow timing windows, inject
sleeps. A 50%-flake bug is debuggable; 1% is not — keep raising the rate
until it's debuggable.

### When you genuinely cannot build a loop

Stop and say so explicitly. List what you tried. Ask the user for: (a)
access to the environment that reproduces it, (b) a captured artifact (HAR
file, log dump, core dump, screen recording with timestamps), or (c)
permission to add temporary production instrumentation. Do **not** proceed
to hypothesise without a loop.

If the answer is still "no loop", Crystallize emits an issue with the
Reproduction block marked `[BLOCKED]` so `/cook` does not silently try
to fix a bug it cannot verify.

## Phase 1 — Reproduce

Run the loop. Watch the bug appear. Confirm:

- The loop produces the failure mode the **user** described — not a
  different failure that happens to be nearby. Wrong bug = wrong fix.
- The failure is reproducible across multiple runs (or, for
  non-deterministic bugs, at a high enough rate to debug against).
- The exact symptom (error message, wrong output, slow timing) is
  captured so later phases can verify the fix actually addresses it.

## Phase 2 — Hypothesize

Generate **3-5 ranked, falsifiable hypotheses** before testing any of
them. Single-hypothesis generation anchors on the first plausible idea.

Each hypothesis takes the form:

> If `<X>` is the cause, then `<changing Y>` will make the bug disappear /
> `<changing Z>` will make it worse.

If the prediction cannot be stated, the hypothesis is a vibe — discard or
sharpen it.

The Hypothesis Probe runs the ranked list as **parallel Validate Cycles**
— one cycle per hypothesis, dispatched simultaneously. The cycle that
returns SUPPORTED with the strongest evidence becomes the working root
cause; cycles that return CONTRADICTED are recorded so future debuggers
can see what was ruled out.

Show the ranked list to the user before running the probe. They often
have domain knowledge that re-ranks instantly ("we just deployed a change
to #3"), or know hypotheses they've already ruled out. Cheap checkpoint,
big time saver.

## Phase 3 — Confirm root cause

The surviving hypothesis becomes the working root cause. Before
Crystallize, the agent must:

- Run the Phase 0 loop again with the working root cause held in mind —
  the prediction the hypothesis makes must match what the loop reports.
- Distinguish "necessary" from "sufficient": is fixing this hypothesis
  enough to make the loop go green, or are there contributing causes?
- If the loop only goes green when **multiple** hypotheses are addressed,
  Crystallize emits one spec for the primary fix plus an issue for each
  contributing cause.

## Hand-off to Crystallize

The bug-shaped spec absorbs:

- **Reproduction block** — the Phase 0 loop, verbatim. Anyone running the
  spec can re-run the loop.
- **Decisions** — the surviving hypothesis as a decision (`Context: ranked
  list of N hypotheses; Decision: cause is X (cycle K SUPPORTED);
  Consequences: fix touches Y`).
- **Interface Sketches** — only if the fix shape requires a new seam or
  changes a public signature. Trivial fixes skip Sketch.
- **Open Questions** — every CONTRADICTED hypothesis stays as `[?]` for
  posterity unless the user explicitly drops it.

Follow-up bugs spotted along the way (out-of-scope to the primary fix)
become **issues** with their own Reproduction blocks (each with its own
loop, even if just "TBD: needs a loop before fix").

## Anti-patterns

- Skipping Phase 0 because "I already know what's wrong". The loop is
  what makes the diagnosis falsifiable; without it, the agent is just
  asserting.
- Generating one hypothesis and confirming it. Ranked lists exist
  because cheap eliminations are how you avoid expensive wrong fixes.
- Treating a flaky loop as a real loop. Flake is a symptom of a loop
  that hasn't been iterated on yet.
- Letting Diagnose write code. The fix is `/cook`'s job; Diagnose
  produces the spec that lets `/cook` verify the fix.
