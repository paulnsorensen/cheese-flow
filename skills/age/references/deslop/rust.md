# Rust De-slop Patterns

Language-specific patterns the `age-deslop` dim looks for in Rust diffs.
Read alongside `protocol.md` (cross-language patterns).

---

## 1. Excessive `.clone()` to Silence the Borrow Checker

LLMs reach for `.clone()` as a universal fix for ownership errors.

**What to look for:** `.clone()` on a value that is immediately passed to
a function that could accept a borrow; repeated `.clone()` chains.

**Fix shape:**
- Use borrowing (`&` and `&mut`) instead
- Take `&str` instead of `String` in function parameters
- Use `.as_ref()` on `Option`/`Result` instead of cloning to unwrap
- Rule: `.clone()` is suspect unless you can explain why you need owned data

```rust
// SLOP
fn greet(name: String) { println!("Hello, {name}"); }
let msg = my_string.clone();
greet(msg);

// CLEAN
fn greet(name: &str) { println!("Hello, {name}"); }
greet(&my_string);
```

---

## 2. `.unwrap()` Everywhere

Creates runtime panics scattered throughout the codebase.

**What to look for:** `.unwrap()` outside of test code or compile-time-guaranteed
constants; `.unwrap()` on I/O operations, network calls, or user input.

**Fix shape:**
- Use `?` operator for error propagation
- Use `anyhow` or `thiserror` for structured errors
- Use `if let Some(x)` or `match` for `Option` types
- `.unwrap()` only for compile-time guarantees (hardcoded regex, constants)

```rust
// SLOP
let file = File::open("config.toml").unwrap();
let config: Config = toml::from_str(&contents).unwrap();

// CLEAN
let file = File::open("config.toml")?;
let config: Config = toml::from_str(&contents)?;
```

---

## 3. Treating Everything as `String`

Losing type safety and adding unnecessary allocations.

**What to look for:** Functions accepting `String` parameters where `&str`
would work; no newtypes for domain identifiers.

**Fix shape:**
- Accept `&str` or `impl AsRef<str>` in function parameters
- Use `Cow<'_, str>` when sometimes owned, sometimes borrowed
- Create newtypes for domain concepts: `struct UserId(String)`

```rust
// SLOP
fn find_user(id: String, name: String) -> String { ... }

// CLEAN
fn find_user(id: &UserId, name: &str) -> Result<User> { ... }
```

---

## 4. Index-Based Loops Instead of Iterators

C-style `for i in 0..vec.len()` misses safety and optimization.

**What to look for:** `for i in 0..items.len()` with `items[i]` indexing;
index arithmetic that could be `.enumerate()` or `.zip()`.

**Fix shape:**
- Use `.iter()`, `.map()`, `.filter()`, `.enumerate()`, `.collect()`
- Use slice patterns: `match vec.as_slice() { [first, ..] => ... }`

```rust
// SLOP
for i in 0..items.len() {
    process(i, &items[i]);
}

// CLEAN
for (i, item) in items.iter().enumerate() {
    process(i, item);
}
```

---

## 5. Fighting Lifetimes with `Rc<RefCell<T>>`

When ownership gets complex, AI reaches for interior mutability or `unsafe`.

**What to look for:** `Rc<RefCell<T>>` for data that doesn't need shared
ownership; `unsafe` blocks in application code (not FFI).

**Fix shape:**
- Reduce borrow lifetimes so they don't overlap
- Design structs to own their data
- Pass short-lived borrows as method parameters
- Restructure to avoid holding long-lived references

---

## 6. Weak Assertions in Test Code

`assert!(result.is_ok())` and `assert!(result.is_err())` swallow the actual
error/value on failure, printing only `false`.

**What to look for:** `assert!(x.is_ok())`, `assert!(x.is_some())`, bare
`assert_eq!` without failure messages on non-obvious operands.

**Fix shape:**
- Propagate with `.expect("context")` or `?` to see the real error
- Check actual values, not just existence
- For errors, verify the specific variant with `matches!` or check the message
- Every `assert_eq!`/`assert!` with non-obvious operands needs a failure message

```rust
// SLOP
assert!(result.is_ok());
assert_eq!(count, 3);  // no context on failure

// CLEAN
let value = result.expect("scan_worktree should succeed");
assert_eq!(value.label, "Ready");
assert_eq!(count, 3, "expected 3 active workers after spawn");
```

---

## 7. `is_none()` / `is_some()` Without Value Context

`assert!(x.is_none())` prints `assertion failed: false`. `assert_eq!` shows
what was actually there.

**What to look for:** `assert!(x.is_none())` or `assert!(x.is_some())` as
sole assertions without extracting the inner value.

**Fix shape:**
- Use `assert_eq!(x, None)` for better failure messages
- For `is_some()`, extract and check the inner value

```rust
// SLOP
assert!(x.is_none());
assert!(ping["result"]["host_type"].as_str().is_some());

// CLEAN
assert_eq!(x, None);
assert_eq!(ping["result"]["host_type"].as_str(), Some("daemon"));
```

---

## 8. Async Timing Slop

Raw `tokio::time::sleep` before assertions is fragile — passes on fast
machines, flakes in CI.

**What to look for:** `sleep(Duration::from_millis(N))` immediately before
an assertion that checks state changed by a concurrent task.

**Fix shape:**
- Use a `wait_until_async` polling pattern with timeout
- Sleep-then-assert is only acceptable for testing actual timing behavior

```rust
// SLOP
tokio::time::sleep(Duration::from_millis(500)).await;
assert_eq!(state.status(), "ready");

// CLEAN — poll with timeout
wait_until_async(Duration::from_secs(2), || async {
    state.status() == "ready"
}).await.expect("status should reach ready");
```

---

## 9. `#[should_panic]` Without `expected`

A bare `#[should_panic]` passes on *any* panic — including unrelated ones
from refactoring. Always pin the expected message.

**What to look for:** `#[should_panic]` without an `expected = "..."` argument.

**Fix shape:**

```rust
// SLOP
#[test]
#[should_panic]
fn rejects_empty_input() {
    parse("");
}

// CLEAN
#[test]
#[should_panic(expected = "input must not be empty")]
fn rejects_empty_input() {
    parse("");
}
```

---

## 10. No-Crash-Is-Success Tests

Tests with zero assertions only prove the code doesn't panic — not that it works.

**What to look for:** Test functions with no `assert*!` macros and no `?`
returning a value; test functions that call a function and return nothing.

**Fix shape:**
- Add assertions on return values or side effects
- If intentionally testing "no panic", add an explicit comment documenting why

```rust
// SLOP
#[test]
fn stamp_activity_nonexistent_is_noop() {
    tracker.stamp_activity("ghost-id");
}

// CLEAN — document the intent
#[test]
fn stamp_activity_nonexistent_is_noop() {
    // No assertion needed: verifying no panic on missing ID
    tracker.stamp_activity("ghost-id");
}
```

---

## 11. Lint Suppression as Band-Aid (`#[allow(...)]`)

AI sprinkles `#[allow(...)]` to silence warnings instead of fixing root causes.

### Crate-Level Nuclear Options (flag immediately)

```rust
// SLOP — nuclear options
#![allow(warnings)]
#![allow(clippy::all)]

// SLOP — scaffold dump (3+ together = AI signature)
#![allow(dead_code)]
#![allow(unused_imports)]
#![allow(unused_variables)]
```

### The AI Scaffold Cluster

| Attribute | AI Excuse | Real Fix |
|-----------|-----------|----------|
| `allow(dead_code)` | "I'll wire it up later" | Delete unconnected code |
| `allow(unused_imports)` | Copied from examples | Remove unused `use` statements |
| `allow(unused_variables)` | Bound "just in case" | Prefix with `_` or remove |
| `allow(unused_mut)` | Added `mut` preemptively | Remove unnecessary `mut` |
| `allow(unused_assignments)` | Assign then overwrite | Remove dead assignment |

### Clippy Suppression Smells

**Red Flag (almost always slop):**

```rust
// Hiding panic risks
#[allow(clippy::unwrap_used)]
#[allow(clippy::expect_used)]
#[allow(clippy::indexing_slicing)]
#[allow(clippy::panic)]

// Incomplete code in CI
#[allow(clippy::todo)]
#[allow(clippy::unimplemented)]
#[allow(clippy::dbg_macro)]

// Logging-aware code ignored
#[allow(clippy::print_stdout)]
#[allow(clippy::print_stderr)]

// Weak error handling
#[allow(clippy::result_unit_err)]
```

**Yellow Flag (context-dependent):**

```rust
#[allow(clippy::too_many_arguments)]
#[allow(clippy::too_many_lines)]
#[allow(clippy::cognitive_complexity)]
```

### Tier System

| Category | Philosophy | Suppression OK? |
|----------|-----------|-----------------|
| **restriction** | "Don't do this" | Almost never |
| **correctness** | "This is likely wrong" | Almost never |
| **complexity** | "This is confusing" | With justification |
| **perf** | "This is slow" | Document why |
| **style** | "Use X instead" | Preference |
| **pedantic** | "Extra strict" | Usually OK |

### Legitimate Uses (do not flag)

- `#[allow(clippy::unwrap_used)]` in test code (idiomatic)
- `#[allow(non_snake_case)]` in FFI modules matching C signatures
- `#[allow(dead_code)]` on test utility functions
- `#[allow(clippy::cognitive_complexity)]` on legitimate state machines

### Scope Rule

The further an allow reaches, the worse it smells. Crate-level > module-level
> function-level > statement-level. If you must allow, scope it narrowly and
add a comment explaining why.

---

## 12. Hallucinated APIs and Deprecated Syntax

AI generates functions that don't exist or uses outdated API patterns
(e.g., `clap` `App::new` instead of derive macros).

**What to look for:** Method calls that don't exist in the current crate version;
API patterns from 2+ major versions ago.

**Fix shape:** Run `cargo check` immediately after generating code. Pin specific
crate versions. Use Clippy. When in doubt, check docs.
