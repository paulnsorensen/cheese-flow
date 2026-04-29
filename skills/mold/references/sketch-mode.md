# Sketch mode — interface lockdown

Sketch is the cognitive job of turning a chosen approach into pseudocode
signatures and contracts. It is **not** writing code. It is plan, expressed
in a shape `/fromage` can compile into target idioms.

## Entry

Enter Sketch when:

- Shape picked an option, OR
- The starting input was already a half-baked design doc with signatures.

If Sketch is mandatory (chosen option touches more than one module or
introduces a new public interface) and the user tries to skip to Crystallize,
the coherence gate blocks the handshake until Sketch runs.

## The pseudocode-driven question pattern

For each public seam, the agent:

1. **Drafts a signature** with named arguments and a return type.
2. **Names the unknowns** — places where a decision is needed.
3. **Recommends an answer** for each unknown, with one-line rationale.
4. **Invites compact confirmation** (`1A 2A`) or push-back.

Example:

```
Draft signature for the dispatcher:

    def dispatch_notification(
        recipient: NotificationRecipient,
        payload: NotificationPayload,
        idempotency_key: str,             # ← unknown #1
    ) -> DeliveryReceipt:                  # ← unknown #2

Unknowns:
  1. `idempotency_key: str` — caller-generated or middleware-injected?
     I'd say caller-generated. The caller owns "what counts as the same event."
  2. Return — sync `DeliveryReceipt` or async event?
     I'd say async. The receipt becomes a `NotificationDelivered` event.

Push back on either, or `1A 2A` to confirm.
```

## Pseudocode style

- **Python-flavored** as the universal shape (function-style signatures,
  type hints). `/fromage` translates to the target language at implement
  time.
- **Names + types + contracts.** Not bodies. Not implementations.
- **Error shape** is part of the contract — name the exception or result
  variants explicitly when failure is part of the seam.
- **Side effects** declared at signature level when they cross a slice
  boundary ("emits `NotificationDelivered`", "reads from `dedup_cache`").

## Sibling sweep

Before drafting a signature for a module, run a **parallel** `cheez-search`
for nearby siblings in the same domain so new signatures fit the
conventions already there.

```
Parallel sketches sweep:
  cheez-search query: "dispatch" scope: "src/notifications/"
  cheez-search query: "queue, enqueue" scope: "src/notifications/"
  cheez-deps path: "src/notifications/index.ts"
```

If the sweep surfaces a sibling that mirrors what we are about to design,
adopt the sibling's shape unless there is a stated reason to diverge.

## Validate Cycle inside Sketch

When a signature mirrors an external API ("our `dispatch` matches Stripe's
`PaymentIntent.create` shape"), invoke a Validate Cycle on that hypothesis
before locking the signature. Common cycles:

- "Library X exposes `<method>(<args>) -> <return>`."
- "Convention Y in our codebase puts `<arg>` in the body, not the headers."
- "Sibling Z returns `<type>` rather than `<other type>`."

## Output

Sketches live in the state file's `Sketches (locked interfaces)` block
during the loop, then migrate verbatim into the spec's `Interface Sketches`
section at Crystallize. Each sketch carries:

- `module` — slice or path.
- `signature` — pseudocode block.
- `responsibilities` — bullet list (1-3 items).
- `seams` — named external integrations (queue, cache, event bus, ...).
- `error shape` — exceptions or result variants.

## Exit

Exit Sketch when **every** public seam touched by the chosen option has a
signature and every cross-module call has a contract. Trivial single-function
changes can skip Sketch entirely; the agent must say so explicitly so the
coherence gate records the override.

## Anti-patterns

- Drafting code, not signatures. Sketch is plan.
- Skipping the sibling sweep, then producing a signature that fights existing
  conventions.
- Locking a signature without a Validate Cycle when it mirrors an external
  API.
- Leaving unknowns implicit instead of named with a recommended answer.
