# Pydantic lax coercion at the manifest boundary

The manifest loader delegates validation to pydantic rather than hand-rolling checks: `ConfigDict(extra="forbid")` rejects unknown keys, `Literal[...]` rejects unknown harness and component names, and `tuple[HarnessName, ...]` rejects non-lists and non-string items. One check must **not** be delegated, and it looks redundant next to the constraint beside it.[^1]

## `Field(ge=0)` does not reject `true` or `"3"`

Pydantic v2's default (lax) mode coerces before it validates bounds. For an `int` field:

- `True` → `1`
- `"3"` → `3`

Both then pass `ge=0` cleanly. A TOML manifest containing `max_depth = true` or `max_depth = "3"` would load, with the boolean silently becoming a depth of 1.

So the explicit bool/str guard in the loader stays, even though the model already carries `Field(ge=0)`. The two do different jobs: the guard constrains the *type* the TOML document may supply, the constraint bounds the *value* the model accepts. Removing the guard as duplicate work widens a trust boundary without changing a single test's outcome.

Strict mode on the field would be the alternative, but it changes the error shape the loader reconstructs for operators; the guard was kept for that reason.

## Deleting hand-rolled validation is otherwise safe — verify it, don't assume it

When the redundant checks were removed, the replacement was verified by running 26 manifest shapes through the old and new loaders side by side: 21 produced byte-identical error messages, 5 differed, and **none** were weaker — no input rejected before is accepted now. Two of the differences are improvements (all errors reported rather than short-circuiting on the first; a wrong-typed harness list now names the unknown value instead of complaining about the array type).

Repeat that comparison rather than trusting that pydantic "obviously" covers a hand-rolled check. The `max_depth` case is exactly the one that looks obvious and is not.

## Operator-facing messages are reconstructed, not inherited

Because the loader is a trust boundary with tested error messages, `_describe` maps pydantic error `type` strings (`extra_forbidden`, `literal_error`, `missing`, `model_type`, `tuple_type`, `path_type`, `greater_than_equal`) back to the project's own wording, using `error.errors()[i]["loc"]` to name the offending key.

The residual risk: a pydantic upgrade that renames an error `type` falls through to the generic branch and quietly degrades a message to pydantic's raw text. A test asserting each mapped `type` string still exists would pin it.

## References

[^1]: `python/cheese_flow/desired_state.py` (the loader, its retained `max_depth` guard, and `_describe`); `python/cheese_flow/models.py` (`max_depth` and its `Field(ge=0)` constraint); `tests/python/test_desired_state.py` covers the rejection cases and the reconstructed messages.
