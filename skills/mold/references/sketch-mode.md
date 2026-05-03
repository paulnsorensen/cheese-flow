# Sketch mode — interface lockdown

Sketch is the cognitive job of turning a chosen approach into pseudocode
signatures and contracts. It is **not** writing code. It is plan, expressed
in a shape `/cook` can compile into target idioms.

## Entry

Enter Sketch when:

- Shape picked an option, OR
- The starting input was already a half-baked design doc with signatures.

If Sketch is mandatory (chosen option touches more than one module or
introduces a new public interface) and the user tries to skip to Curdle,
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

## Slice placement

Every signature names the **Sliced Bread slice** it lives in before the
pseudocode is drafted. The slice — `domains/<name>`,
`adapters/<name>`, `app`, or `domains/common` — goes in the sketch's
`slice` field. The `module` field records the specific file or module
path within that slice.

Default decisions:

- **Pure business concept** (entity, value type, port) → `domains/<name>`.
  Define the port inside the domain; adapters implement it.
- **External integration** (DB, third-party SDK, queue, cache, logger) →
  `adapters/<name>`. Implements a port from `domains/`.
- **Cross-slice orchestration** (use case spanning 2+ domain slices) →
  `app/use_cases`.
- **Pure shape with universal semantics** (Money, UserId, Email) →
  `domains/common`. Only when the type has zero behavior and is referenced
  by 2+ slices today.

Full rules in `references/sliced-bread.md` (repo root, not local to this
skill). The Sketch gate fails if any signature crosses an existing
slice's boundary by importing internals instead of the crust, or if
`domains/common` would import from a sibling slice.

When the chosen option crosses an existing slice's crust, the sketch
records the imported public name (`from domains.orders import dispatch`)
rather than reaching into internals. Run a Validate Cycle on the import
target to confirm it actually appears in the slice's index file before
locking the signature.

## Pseudocode style

- **Python-flavored** as the universal shape (function-style signatures,
  type hints). `/cook` translates to the target language at implement
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
  cheez-search query: "dispatch" scope: "domains/notifications/"
  cheez-search query: "queue, enqueue" scope: "domains/notifications/"
  cheez-search query: "dispatch" kind: "callers" scope: "src/"
  cheez-search deps: "domains/notifications/index.ts"
```

`cheez-search` exposes both `tilth_search` (definitions, usages, callers)
and `tilth_deps` (imports, imported-by). The blast-radius and sibling
work happens through that single skill.

If the sweep surfaces a sibling that mirrors what we are about to design,
adopt the sibling's shape unless there is a stated reason to diverge.

## NIH probe

Before locking a signature for any of the **library-shaped categories**
below, run an NIH probe — a single Validate Cycle that asks "is this a
wheel that's already been invented?":

| Category | Trigger words in the sketch |
|----------|------------------------------|
| `RETRY` | retry, backoff, exponential, jitter |
| `VALIDATION` | validate, schema, isEmail, isUrl, regex check |
| `UUID` | uuid, guid, randomId, generateId |
| `DEBOUNCE` | debounce, throttle, rate-limit |
| `DATE` | parseDate, formatDate, addDays, diffMinutes |
| `ARGPARSE` | argv, parseArgs, CLI flags |
| `CLONE` | deepClone, cloneDeep, structuredClone |
| `STRING` | slugify, kebabCase, snakeCase, truncate |
| `CRYPTO` | hashPassword, verifyPassword |
| `SECURITY` | sanitizeHtml, escapeHtml |
| `FORMAT` | formatCurrency, formatNumber, Intl wrapper |

Probe shape (anchored as a Validate Cycle so the framing matters):

```
Launching a validate cycle on hypothesis:
  "Library X already does <category>; we should not hand-roll a sketch for it."

Plan:
  cheez-search — confirm we don't already depend on X (depManifest check).
  /research    — fetch the canonical library for this category in <language>;
                 prefer stdlib answers; capture downloads + licence + maintenance.
  Judge        — does the library cover the contract we're about to sketch?
  Settle       — accept (use library, drop sketch), revise (sketch wraps lib),
                 or reject (NIH is intentional; record reason in Decisions).
```

Cap: at most **one** NIH probe per Sketch session (in addition to the
shared 2-`/research` budget). Use the probe only for library-shaped
categories — pure business-domain signatures (an Order, a Pricing rule)
do not need it.

If the probe verdict is **accept**, drop the sketch entirely and replace
it with a thin call-site note (`use library X for <category>`). If
**revise**, the sketch becomes a wrapper signature whose body delegates
to the library — record `wraps: <library>` in the sketch's `seams` block.
If **reject**, log the reason in `Decisions` so `/age`'s `nih` dim does
not flag it later.

For a whole-spec build-vs-buy sweep (multiple library-shaped categories
across the chosen option), prefer a single `/nih-audit <scope>` call
over N probes — and record one Decision rolling up its findings.

### Migration hand-off

A spec is "migration-shaped" when its `Decisions` block contains an NIH
probe verdict of `accept` or `revise` — i.e. the dialogue agreed to drop
or wrap a hand-rolled implementation. In that case the next step is a
whole-repo `/nih-audit` so the migration finds every other call site, not
just the one that triggered the probe. The Curdle hand-off table in
`SKILL.md` routes that path automatically.

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
section at Curdle. Each sketch carries:

- `module` — slice path or file path.
- `slice` — Sliced Bread slice (`domains/<name>`, `adapters/<name>`, `app`, or `domains/common`).
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
