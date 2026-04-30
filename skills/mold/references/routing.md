# Routing — input shape to starting mode

`/mold` chooses one starting mode on entry. The agent announces the choice
in one line so the user can override (`explore`, `ground`, `shape`, ...).

## Classifier

Walk the heuristics top-down. The **first** match wins.

1. **Diagnose** — the input contains:
   - Stack frames or `file.ext:NNN` references plus an exception or error
     keyword (`TypeError`, `panic`, `Traceback`, `Exception`, ...), OR
   - Symptom verbs combined with a subject ("X is broken", "Y is slow",
     "Z hangs", "flaky", "crashing", "intermittent failure").
2. **Ground** — the input is, or points at, a concrete artifact:
   - File path that exists in the repo, OR
   - PR or issue reference (URL, `#1234`), OR
   - A spec path under the active harness root, OR
   - "Read X and tell me ..." style requests.
3. **Sketch** — the input contains existing structure to refine:
   - Fenced code blocks containing function signatures or schemas, OR
   - "Here's my draft design ..." with module names and contracts, OR
   - The user explicitly asks "lock down the interfaces for ...".
4. **Shape** — the input names a concrete *thing* to add or change:
   - "I want to add ...", "Let's build ...", "We should support ..." with
     concrete nouns, OR
   - The user explicitly asks for options ("give me options", "how should
     I approach ...").
5. **Grill** — the input is a tentative plan looking for stress-testing:
   - "Should we do X?", "I'm thinking about Y", "Is this approach sane?",
     OR
   - The user explicitly asks "interrogate this" / "poke holes".
6. **Explore** — default fallback for vague nouns, half-sentences, "thinking
   about", or anything that did not match above.

## Confidence

Score the chosen mode 0-100 from the strength of its trigger:

- 90+ — multiple strong signals (stack trace + file:line + error keyword).
- 60-89 — single strong signal (named artifact, named approach + nouns).
- 40-59 — soft signal only (vague noun + tentative verb).
- < 40 — no clear signal; default to **Explore** regardless.

If confidence is below 60, announce the mode plus the alternative the agent
considered, and explicitly invite a knob redirect.

## Examples

| Input | Mode | Reason |
| --- | --- | --- |
| `TypeError: cannot read property 'foo' of undefined at app.ts:142` | Diagnose | error keyword + file:line |
| `.cheese/specs/dark-mode.md` | Ground | spec path; read first |
| `def dispatch(...): ... # what should the return type be?` | Sketch | existing signature with question |
| `I want to add idempotency to the dispatcher` | Shape | concrete noun, additive verb |
| `Should we extract the dedup layer into its own slice?` | Grill | tentative verb on a plan |
| `thinking about how we handle retries someday` | Explore | hedged, no chosen direction |

## Pivots

A user knob immediately changes mode. The classifier only runs at entry —
mid-session pivots come from knobs or from the agent surfacing a guard
condition (e.g. "we have not Grounded yet; switching to Ground for one pass").
