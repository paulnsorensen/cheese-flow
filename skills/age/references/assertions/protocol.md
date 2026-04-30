# Weak Assertion Patterns — Cross-Framework Protocol

Patterns the `age-assertions` dim looks for during `/age` review of test files.
Applies across all test frameworks; supplement with the language-specific
reference for the test framework present in the diff.

The dim only applies when the diff contains test files. When no test files are
touched, emit `{"observations": [], "scope_match": false}`.

---

## 1. Existence Check Instead of Value Equality

The #1 AI testing failure. Asserts something exists without verifying it's correct.

**What to look for:** `assert result is not None`, `expect(result).toBeDefined()`,
`assert!(result.is_some())`, `assert.NotNil(t, result)` — any assertion that
only checks presence.

**Fix shape:** Always assert the specific value expected, not just that a value
exists.

```
WEAK: assert result is not None
STRONG: assert result == expected_value

WEAK: expect(result).toBeDefined()
STRONG: expect(result).toEqual({ id: 1, name: "Alice" })

WEAK: assert!(result.is_some())
STRONG: assert_eq!(result.unwrap(), expected)
```

---

## 2. Length Check Without Content Inspection

Verifies the container has items but not what those items are.

**What to look for:** `assert len(results) == 1`, `expect(items).toHaveLength(3)`,
`assert_eq!(vec.len(), 2)`, `assert.Equal(t, 2, len(results))` — any
assertion that only checks the count.

**Fix shape:** Check content first. Length-only assertions are acceptable as
a *final* confirmation after content checks, never as the sole assertion.

```
WEAK: assert len(results) == 1
STRONG: assert results[0].name == "Alice"

WEAK: expect(items).toHaveLength(3)
STRONG: expect(items).toEqual([...expected])
```

---

## 3. Catch-All Error Assertions

Verifies an error occurred without checking it's the *right* error.

**What to look for:** `pytest.raises(Exception)`, `expect(() => fn()).toThrow()`,
`assert!(result.is_err())`, `assert.Error(t, err)` — any assertion that
accepts any error.

**Fix shape:** Assert the specific error type AND message/content.

```
WEAK: with pytest.raises(Exception):
STRONG: with pytest.raises(ValueError, match=r"must be positive"):

WEAK: expect(() => fn()).toThrow()
STRONG: expect(() => fn()).toThrow(ValidationError)

WEAK: assert!(result.is_err())
STRONG: assert!(matches!(result, Err(MyError::NotFound(_))))
```

---

## 4. No-Crash-as-Success

Test only asserts the function didn't throw, with no behavioral check.

**What to look for:** Test functions where the only assertion is the absence
of an error, or test functions with no assertions at all.

**Fix shape:** Every test needs a positive behavioral assertion. "Didn't crash"
is necessary but never sufficient.

```
WEAK: run my_command; assert_success  (sole assertion)
STRONG: run my_command; [[ "$output" == "expected" ]]

WEAK: require.NoError(t, err)  (nothing follows)
STRONG: require.NoError(t, err); assert.Equal(t, expected, result)
```

---

## 5. Mock Verification Without Arguments

Verifies a mock was called but not *how* it was called.

**What to look for:** `mock_fn.assert_called()`, `expect(mockFn).toHaveBeenCalled()`,
`mock.AssertCalled(t, "Send")` — any verification that ignores arguments.

**Fix shape:** Always verify mock call arguments. A mock called with wrong
arguments is a test that passes while the code is broken.

```
WEAK: mock_fn.assert_called()
STRONG: mock_fn.assert_called_once_with(user_id=42, role="admin")

WEAK: expect(mockFn).toHaveBeenCalled()
STRONG: expect(mockFn).toHaveBeenCalledWith({ to: "alice@example.com" })
```

---

## 6. Testing the Mock, Not the Code

Asserts that a mock returns what you told it to return — tautological.

**What to look for:** Test code that calls the mock directly and asserts it
returns its configured `return_value`.

**Fix shape:** The assertion should check the *system under test* which *uses*
the mock, not the mock itself.

```
WEAK:
  mock = Mock(return_value=42)
  assert mock() == 42  # Tests Mock.__call__, not your code

STRONG:
  mock_repo = Mock(return_value=42)
  service = MyService(repo=mock_repo)
  result = service.do_thing()
  assert result == expected_output
```

---

## 7. Boolean Coercion Assertions

Uses truthiness where a value check is possible and more precise.

**What to look for:** `assert bool(result)`, `expect(!!result).toBe(true)`,
`assert!(some_function())` — assertions that coerce to boolean.

**Fix shape:** If you know what the value should be, assert that. Truthiness
only when the contract genuinely is "any truthy value."

```
WEAK: assert bool(result)
STRONG: assert result == expected_value

WEAK: assert!(some_function())
STRONG: assert_eq!(some_function(), expected)
```

---

## 8. Tautological Assertions

Assertions that literally cannot fail. A test that always passes tests nothing.

**What to look for:** `assert True`, `expect(1).toBe(1)`, `assert_eq!(true, true)`,
`[[ $status -eq 0 || $status -eq 1 ]]`.

**Fix shape:** Delete tautological assertions. If the test needs a placeholder,
mark it as `@pytest.mark.skip` / `it.todo()` / `#[ignore]` instead.

---

## 9. Approximate Equality When Exact Is Possible

Uses fuzzy matching when the result is deterministic.

**What to look for:** `assertAlmostEqual`, `toBeCloseTo`, epsilon comparisons
on results of integer arithmetic, string operations, or deterministic
calculations.

**Fix shape:** Use approximate equality only for floating-point arithmetic
that genuinely introduces rounding. Integer math and deterministic
calculations should use exact equality.

```
WEAK: assert abs(result - 100) < 1      (result IS exactly 100)
STRONG: assert result == 100

WEAK: expect(result).toBeCloseTo(100)   (when result is integer math)
STRONG: expect(result).toBe(100)
```

Reverse is also a smell: using `assert_eq!` on computed float values that
may legitimately differ by tiny amounts due to rounding.
