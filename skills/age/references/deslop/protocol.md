# De-slop Patterns — Cross-Language Protocol

Patterns the `age-deslop` dim looks for during `/age` review. Applies to
all languages; supplement with the language-specific reference for the
languages present in the diff.

---

## 1. Comment Pollution

AI explains *what* code does instead of *why*. Every function gets a docstring.
Every line gets a narration comment.

**What to look for:** Comments that restate the code verbatim; docstrings that
repeat the function name; inline narration of obvious operations.

**Fix shape:** Delete comments that restate the code. Keep only comments that
explain non-obvious intent, business rules, or "why not the obvious approach."

---

## 2. Defensive Error Handling Everywhere

Try/catch wrapping every operation, swallowing errors silently, returning
empty defaults instead of propagating failures.

**What to look for:** Catch blocks with `pass`/`return {}`/`return null`; errors
consumed without logging or re-raise; functions that return sentinel values
on failure where the caller has no way to distinguish success from silent error.

**Fix shape:** Let errors propagate to where they can be handled meaningfully.
A function that returns `{}` on failure is worse than one that throws — the
caller silently gets corrupted data.

---

## 3. Over-Abstraction

Abstract base classes, interfaces, factory functions, and plugin systems for
problems with exactly one concrete implementation.

**What to look for:** Single-implementor interfaces; factory functions that
create exactly one type; abstract classes with one subclass; plugin registries
with one plugin.

**Fix shape:** Delete the abstraction. Write the concrete implementation directly.
Three similar lines of code is better than a premature abstraction. Extract
only when there are 3+ real consumers.

---

## 4. Verbose Names That Describe Types, Not Domain

`user_data_dictionary`, `list_of_user_objects`, `current_item_being_processed`.
These names couple to the data structure and add noise.

**What to look for:** Names that embed their container type (`_list`, `_dict`,
`_array`, `_map`, `_slice`); names with `current_` or `_being_processed` scaffolding.

**Fix shape:** Name after the domain concept: `users`, `items`, `user`.
A name should tell you what the thing *represents*, not what container it lives in.

---

## 5. Unnecessary Type Annotations

Annotating local variables where the type is immediately obvious from the
right-hand side. Function signatures deserve annotations; `const x: number = 5` doesn't.

**What to look for:** Type annotations on variables initialized with literals,
constructor calls, or typed function return values where inference is unambiguous.

**Fix shape:** Remove annotations where inference handles it. Keep them on
function signatures (they're the public contract) and where the inferred type
would be unclear. Empty collection declarations are an exception — inference
can't know the element type.

---

## 6. Dead Code and Unused Imports

AI imports entire module sets "just in case" and leaves commented-out
alternative implementations.

**What to look for:** Unused imports (any language); commented-out alternative
implementations; functions defined but never called; variables assigned but
never read.

**Fix shape:** Delete unused imports and dead code. No `// Alternative approach:`
blocks. If it's not called, it's not code.

---

## 7. Cargo-Cult Boilerplate

Patterns copied without understanding: `if __name__ == "__main__":` in every
Python file, `"use strict"` in TypeScript, `context.TODO()` in non-concurrent
Go paths.

**What to look for:** Boilerplate that appears in every file regardless of
whether it's needed; patterns applied out of habit without the condition they guard.

**Fix shape:** Remove boilerplate that serves no purpose in context. Apply
patterns only where they're needed.

---

## 8. Test Bloat

AI generates many shallow tests covering the same code path with slightly
different inputs — all testing the same behavior, none adding new coverage.

**What to look for:** Multiple test functions with minor input variations testing
the same logic path; test suite size dramatically exceeding implementation size;
no tests for error paths or edge cases despite many happy-path tests.

**Fix shape:** Consolidate into parameterized/table-driven tests. One test per
behavior, not one test per input variation. Focus tests on actual edge cases
and error paths.

---

## 9. Lint Suppression as Band-Aid

AI silences compiler/linter warnings with suppression comments instead of fixing
the underlying issue: `#[allow(dead_code)]`, `# noqa`, `// @ts-ignore`,
`//nolint`, `// eslint-disable`.

**High-confidence smells (almost always slop):**
- Rust: `#[allow(clippy::unwrap_used)]`, `#[allow(clippy::dbg_macro)]`, `#[allow(clippy::print_stdout)]`, `#[allow(clippy::panic)]`, `#[allow(clippy::todo)]`
- Python: `# noqa: E501`, `# pylint: disable=missing-docstring`
- TypeScript: `// @ts-ignore` (without `@ts-expect-error`)
- Go: `//nolint` without specific lint name
- Shell: broad `# shellcheck disable=SCxxxx`

**Fix shape:** Remove the suppression, read the warning, fix the root cause.
If suppression is truly needed, scope it narrowly and add a comment explaining why.
See language references for per-language taxonomy (Rust has the deepest).

---

## 10. Partial Strict Mode in Shell Scripts

AI writes `set -e` but omits `-u` (undefined variables) and `-o pipefail`
(pipeline error propagation). Failures in the left side of pipes are silently ignored.

**What to look for:** Shell scripts with `set -e` only; scripts with no `set`
at all; pipes through `jq`/`yq`/`grep` without `pipefail`.

**Fix shape:** Always `set -euo pipefail`. All three flags together.
`set -e` alone is a half-measure.
