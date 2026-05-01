# NIH dim — pattern catalog

The diff-scoped patterns the `age-nih` agent looks for. The standalone
audit's category map at `skills/nih-audit/references/categories.md` is
the canonical superset; this file lists only the patterns that surface
cleanly in a single PR's added/modified lines.

## Tier-1 patterns (diff-flaggable)

1. **Hand-rolled UUID** — new `Math.random().toString()` constructions,
   manual `xxxxxxxx-xxxx-4xxx` template strings, or any
   `generateUuid`/`uuidv4` function added when `crypto.randomUUID()`
   (browser/Node) or `uuid::Uuid` (Rust) covers it.
2. **JSON deep-clone hack** — new `JSON.parse(JSON.stringify(...))`
   introduced when `structuredClone` (stdlib in modern Node/browsers)
   covers the case.
3. **Custom retry/backoff** — new `for/while` loops with `try/catch` +
   sleep in their body, introduced in a project that already depends on
   a retry library (`p-retry`, `tenacity`, `backoff`, `tokio-retry`).
4. **Manual debounce/throttle** — new `setTimeout`/`clearTimeout` pairs
   implementing rate-limiting, when `lodash.debounce` or
   `throttle-debounce` is already installed.
5. **Hand-rolled validation** — new regex tests for emails, URLs, UUIDs,
   dates, when the project depends on `zod`, `yup`, `pydantic`,
   `validator`, or similar.
6. **Manual argparse** — new `process.argv.slice(2)` / `sys.argv[1:]`
   parsing added in a project that depends on `commander`, `yargs`,
   `click`, `clap`, `cobra`, etc.
7. **Manual Display/Error/Serialize impls (Rust)** — new
   `impl std::fmt::Display` / `impl Serialize` boilerplate when
   `thiserror` / `serde_derive` would generate it.
8. **Hand-rolled string-case helpers** — new `camelCase` / `snakeCase` /
   `kebabCase` / `slugify` functions when a string-case library is
   already installed.

## Bucket assignment

- **`high`** — stdlib alternative exists (zero new deps required).
  Examples: `crypto.randomUUID`, `structuredClone`, `Intl.NumberFormat`.
- **`med`** — alternative is an already-installed dependency the project
  has not migrated to.
- **`low`** — the alternative would require a new dependency. Surface for
  awareness; the install decision belongs to the reviewer.

## Bucket demotion

If a code comment near the candidate explains the NIH choice
(`intentionally`, `we chose`, `instead of`, `NOTE:`, `DECISION:`),
demote one bucket and quote the comment in `evidence`. If the candidate
is already at `low`, suppress the observation entirely — the comment is
itself sufficient evidence that the reviewer doesn't need to be reminded.

## What never counts as NIH

- Stdlib idioms — `http.Client` (Go), `logging.basicConfig` (Python),
  `timedelta` (Python), `while getopts` (bash), `pathlib`, `dataclasses`.
- Existing NIH being moved or refactored without growth — surface in
  `summary`, not as an observation.
- Pure business-domain signatures (`Order`, `PricingRule`,
  `Fulfilment`) — the NIH dim is build-vs-buy, not naming.

## Cross-reference

The whole-repo audit lives at `skills/nih-audit/SKILL.md` and uses the
canonical category map at `skills/nih-audit/references/categories.md`.
Keep that file as the source of truth for category-to-library pairings;
this file just enumerates the diff-scoped subset the dim flags.
