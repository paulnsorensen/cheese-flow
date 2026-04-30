# Python De-slop Patterns

Language-specific patterns the `age-deslop` dim looks for in Python diffs.
Read alongside `protocol.md` (cross-language patterns).

---

## 1. `range(len())` Instead of `enumerate`

AI defaults to C-style index loops.

**What to look for:** `for i in range(len(items))` when the loop body uses
both `i` and `items[i]`.

```python
# SLOP
for i in range(len(items)):
    print(i, items[i])

# CLEAN
for i, item in enumerate(items):
    print(i, item)
```

When the index is not needed, iterate directly:

```python
for item in items:
    process(item)
```

---

## 2. Manual `None` Checks Instead of Truthiness

**What to look for:** `if user is not None and user.name is not None and len(user.name) > 0`.

```python
# SLOP
if user is not None and user.name is not None and len(user.name) > 0:
    greet(user.name)

# CLEAN
if user and user.name:
    greet(user.name)
```

---

## 3. Old-Style String Formatting

AI mixes `%`, `.format()`, and f-strings inconsistently.

**What to look for:** `%` formatting or `.format()` in code that otherwise
uses f-strings (Python 3.6+).

```python
# SLOP
message = "Hello, %s! You have %d messages." % (name, count)
message = "Hello, {}!".format(name)

# CLEAN — f-strings everywhere (Python 3.6+)
message = f"Hello, {name}! You have {count} messages."
```

---

## 4. Silent `except: pass`

Swallowing exceptions without handling is the #1 debugging time-sink.

**What to look for:** `except Exception: pass`, `except: pass`, catch blocks
that return empty defaults without logging.

```python
# SLOP
try:
    risky_operation()
except Exception:
    pass  # Silent failure

# CLEAN — either handle it meaningfully or don't catch it
# If you truly need to ignore: except SpecificError as e: logger.debug(...)
```

---

## 5. Raw Dicts for Structured Data

AI returns `{"id": 1, "name": "Alice"}` where a dataclass gives type safety,
IDE support, and self-documenting code.

**What to look for:** Functions returning raw dicts with fixed keys that are
always the same shape; callers using string keys to access struct-like data.

```python
# SLOP
def get_user():
    return {"id": 1, "name": "Alice", "email": "alice@example.com"}

# CLEAN
@dataclass
class User:
    id: int
    name: str
    email: str
```

---

## 6. `open()` Without Context Manager

**What to look for:** `f = open(...)` not inside a `with` block; manual
`f.close()` calls.

```python
# SLOP
f = open("file.txt")
data = f.read()
f.close()  # Never reached if f.read() throws

# CLEAN
with open("file.txt") as f:
    data = f.read()
```

---

## 7. Overzealous Type Hints on Obvious Locals

**What to look for:** Type annotations on variables initialized with literals
or unambiguous constructor calls.

```python
# SLOP
name: str = "Alice"
count: int = 0
active: bool = True

# CLEAN — type hints on function signatures, not obvious assignments
name = "Alice"
count = 0
items: list[str] = []  # Empty collection annotation is fine (inference can't know element type)
active = True
```

---

## 8. List Comprehension Where a Generator Suffices

**What to look for:** `sum([x for x in ...])`, `any([x for x in ...])`,
`max([x for x in ...])` — functions that consume iterables building a full
list in memory first.

```python
# SLOP — builds entire list in memory just to iterate
total = sum([x * x for x in range(1_000_000)])

# CLEAN — generator expression, lazy evaluation
total = sum(x * x for x in range(1_000_000))
```
