# NIH categories — canonical map

The category tag the scanner emits, the library shape to look for, and the
research query template for each.

| Category | Library shape | Research query |
|----------|---------------|----------------|
| `RETRY` | retry / backoff library | "best retry/backoff library for {language} (must be MIT/Apache); jitter and exponential backoff support" |
| `UUID` | UUID generator | "recommended UUID library for {language}; check stdlib first (crypto.randomUUID, uuid.uuid4, uuid::Uuid)" |
| `VALIDATION` | schema/regex validator | "best validation library for {language}: zod, pydantic, validator, ozzo, etc." |
| `DATE` | date/time library | "best date/time library for {language}: date-fns, dayjs, chrono, dateutil; check stdlib first" |
| `DEBOUNCE` | debounce/throttle | "debounce/throttle library for {language}; small focused micro-libs preferred" |
| `CLONE` | deep clone | "deep clone library for {language}; check stdlib first (structuredClone, copy.deepcopy)" |
| `ARGPARSE` | CLI argument parser | "argument parsing library for {language}: commander, click, clap, cobra; not stdlib argparse" |
| `STRING` | string-case manipulation | "string-case library for {language}: change-case, lodash.kebabCase, slugify" |
| `HTTP` | HTTP client | "HTTP client library for {language}: axios, requests, reqwest, resty; check stdlib first" |
| `SERIALIZATION` | (de)serializer | "serialization library for {language}: serde, marshmallow, dataclasses-json" |
| `ERROR` | error/result type | "error handling library for {language}: thiserror, anyhow; trait/decorator libraries for boilerplate" |
| `CRYPTO` | password hashing | "password hashing library for {language}: bcrypt, argon2; never roll your own" |
| `SECURITY` | HTML/SQL sanitizer | "HTML sanitization library for {language}: DOMPurify, sanitize-html, bleach" |
| `FORMAT` | number/currency format | "number/currency formatting library for {language}; check stdlib Intl first" |
| `PATH` | path-joining utility | "path joining in {language}; check stdlib first (Node path.join / path.posix.join, Python pathlib.Path, Go filepath.Join, Rust std::path::Path)" |
| `COMPARE` | deep equality | "deep equality library for {language}: fast-deep-equal, lodash.isEqual; check stdlib first" |

## Stdlib-first principle

For every category, check the standard library first. Stdlib alternatives
score `REPLACE_WITH_STDLIB` (base 55, cap 100) — the highest tier — because
they require no new dependency.

| Language | Stdlib wins to remember |
|----------|--------------------------|
| TypeScript / JS | `crypto.randomUUID`, `structuredClone`, `Intl.NumberFormat`, `Array.prototype.flat`, `URL` parsing |
| Python | `uuid`, `copy.deepcopy`, `pathlib`, `dataclasses`, `argparse`, `json`, `re` |
| Rust | `std::time`, `std::path`, `std::env`, derive macros for trivial impls |
| Go | `path/filepath`, `flag` (basic CLI), `time`, `encoding/json`, `crypto/rand` |

## Library quality bar

Reject (cap at 40) when any of:

- Last commit > 1 year ago.
- Fewer than 3 distinct contributors in the last year.
- Open critical security issues without a fix.
- GPL licence in a permissive-licensed project (flag, don't auto-cap).

Prefer when:

- Top result by downloads in its category.
- MIT / Apache-2.0 / BSD licence.
- Active maintainer + recent releases.
- API surface is small and obvious from a single example.
