# Python (pytest) Weak Assertion Patterns

Framework-specific patterns the `age-assertions` dim looks for in Python test diffs.
Read alongside `protocol.md` (cross-framework patterns).

---

## 1. Truthy Instead of Value Equality

The most common AI assertion failure. Any non-empty, non-zero value passes.

```python
# WEAK — None, 0, "" fail; anything else passes
assert result
assert result is not None
assert bool(result)

# STRONG
assert result == {"key": "expected_value"}
assert result == User(id=1, name="Alice")
assert result == [Item(id=1), Item(id=2)]
```

---

## 2. `len()` Without Content Check

Knows there are items, doesn't know if they're the right items.

```python
# WEAK
assert len(results) == 1
assert len(d) > 0

# STRONG — content first, length as confirmation
assert results[0].name == "Alice"
assert results[0].role == "admin"
assert len(results) == 1  # OK as final confirmation
```

---

## 3. `isinstance` Instead of Value Check

Verifies the type but not the data.

```python
# WEAK
assert isinstance(result, list)
assert isinstance(result, User)

# STRONG
assert result == [1, 2, 3]
assert result == User(id=1, name="Alice")
```

---

## 4. `pytest.raises(Exception)` — Catch-All

Any exception passes. Wrong function signature? Passes. Import error? Passes.

```python
# WEAK
with pytest.raises(Exception):
    validate(-1)

with pytest.raises(Exception) as exc_info:
    do_thing()
# exc_info never inspected

# STRONG — specific type AND message
with pytest.raises(ValueError, match=r"must be positive"):
    validate(-1)

# STRONG — inspect exception details
with pytest.raises(ValidationError) as exc_info:
    validate(data)
assert exc_info.value.field == "email"
assert "invalid format" in str(exc_info.value)
```

---

## 5. Mock `.assert_called()` Without Arguments

The function was called — but with what?

```python
# WEAK
mock_send.assert_called()
mock_send.assert_called_once()

# STRONG
mock_send.assert_called_once_with(
    to="alice@example.com",
    subject="Welcome",
    body=ANY,  # OK to use ANY for non-critical args
)
```

---

## 6. `mock.called` Without `assert` — Silent Pass

The real pitfall is referencing `.called` without asserting. It is always
truthy as a bare expression and silently passes.

```python
# WEAK — bare expression, always passes, tests nothing
mock.called

# WEAK — works but only checks "was called", not "with what"
assert mock.called

# STRONG
mock.assert_called_once_with(expected_arg)
```

---

## 7. Testing the Mock Itself

Asserts the mock returns what you configured it to return. Tautological.

```python
# WEAK — tests unittest.mock, not your code
mock_repo = Mock()
mock_repo.find.return_value = User(id=1)
assert mock_repo.find(1) == User(id=1)

# STRONG — test the system that USES the mock
mock_repo = Mock()
mock_repo.find.return_value = User(id=1, name="Alice")
service = UserService(repo=mock_repo)
result = service.get_display_name(1)
assert result == "Alice"
mock_repo.find.assert_called_once_with(1)
```

---

## 8. `assert x in y` for Structured Data

Substring matching on structured output hides mismatches.

```python
# WEAK — "Alice" could appear in error messages, other fields
assert "Alice" in str(result)
assert "success" in response.text

# STRONG
assert result.name == "Alice"
assert response.json() == {"status": "success", "user_id": 42}
```

---

## 9. Unordered Check When Order Matters

Using `set()` comparison when the function should return ordered results.

```python
# WEAK — if sort is broken, this still passes
assert set(result) == {"a", "b", "c"}

# STRONG — when order is part of the contract
assert result == ["a", "b", "c"]

# When order genuinely doesn't matter, be explicit
assert sorted(result) == ["a", "b", "c"]
```
