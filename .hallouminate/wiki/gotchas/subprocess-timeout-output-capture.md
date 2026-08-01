# Subprocess timeout output capture

Two branches in `runner.py` look like the same kind of defensive code around `subprocess` timeouts. One is unreachable and should be deleted; the other is load-bearing and deleting it silently corrupts every captured output. Anyone auditing this file for dead code needs to tell them apart before touching either.[^1]

## The second `communicate()` returns a superset, so the `or` fallback is dead

When the first `communicate()` raises `TimeoutExpired`, the natural pattern is to keep the partial output, kill the child, call `communicate()` again, and fall back to the first result if the second came back empty:

```python
stdout = second_out or drained_out   # the fallback can never fire
```

CPython accumulates read chunks in `Popen._fileobj2output`, and that buffer **persists across `communicate()` calls**. The second `TimeoutExpired` therefore carries a superset of the first: `second_out` is non-empty whenever `drained_out` is, and when `drained_out` is empty the `or` is a no-op. The fallback is unreachable for every possible input.

This is why no mutation test kills it — `stdout = second_out` is *semantically equivalent*, not merely untested. A test written to force the branch would have to fake `subprocess` and would then be asserting against a mock rather than real behavior. Delete the fallback; do not try to cover it.

## `TimeoutExpired.stdout` is `bytes` even under `text=True`, so the decode branch stays

The adjacent trap runs the other way. A decode helper that reads:

```python
if isinstance(value, bytes | bytearray):
    return value.decode(...)
```

reads like the same phantom edge-case handling, but `Popen._check_timeout` builds the exception as `output=b''.join(stdout_seq) if stdout_seq else None`. The payload is `bytes` or `None` **regardless of `text=True`**, which only governs the normal return path. Remove the `isinstance` branch and captured output silently becomes the string `"b'brie'"` — a repr, not the child's actual output — in every timeout report.

Narrow the helper's accepted type to `bytes | None` if you want the contract stated, but keep the decode.

## Why this is recorded

Both branches were logged as one undifferentiated "two defensive branches in `runner.py` are unreachable and are not mutation-killed by their tests" residual risk. Acting on that note as written would delete the load-bearing one. The note needed splitting, and the distinction cost two separate investigations to establish.

## References

[^1]: `python/cheese_flow/runner.py` (the `communicate` retry and `_decode`); `tests/python/test_runner.py` covers the decode contract. CPython behavior verified against the installed `subprocess` module source — `Popen._communicate`'s use of `self._fileobj2output` and `Popen._check_timeout`'s exception construction.
