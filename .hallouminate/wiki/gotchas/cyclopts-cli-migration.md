# cyclopts replaced typer: three behaviors need care

The `cheese` root app and the `profile` subapp use cyclopts, not typer (PR #112). Cyclopts has no drop-in shim. Three call sites carry deliberate workarounds. A like-for-like port loses them.

## Set `negative=""` on every boolean and list option

Cyclopts adds a `--no-<flag>` flag for each boolean `Parameter`. It adds an `--empty-<name>` flag for each list `Parameter`. Typer adds neither. Each `Parameter(...)` in `python/cheese_flow/cli.py` passes `negative=""` to suppress them. A new option without `negative=""` adds an undocumented flag to `--help` and to the parser. Nothing fails, so the gap is silent.

## Exit with `raise SystemExit(code)`, not `typer.Exit`

Cyclopts has no `Exit` exception. The CLI raises `SystemExit(n)` instead. The exit-code contract is unchanged: `0` is success, `1` is failure, and `2` is a manifest or option error. See `_FAILURE_EXIT_CODE` and `_MANIFEST_EXIT_CODE` in `cli.py`. To find exit sites, search for `SystemExit`. A search for `typer.Exit` finds nothing.

## Passthrough launch args use a variadic `Parameter`

The `launch` command in `python/cheese_flow/profiles/cli.py` forwards arguments to the harness. Typer read them from `ctx.args`. Cyclopts has no such context. The command declares `*arguments` with `Parameter(allow_leading_hyphen=True)`. Tokens such as `--foo` and `-x` then reach the harness. The `launch` command does not parse them as its own options.

## The test runner is hand-rolled

Cyclopts ships no test runner. `tests/python/cyclopts_testing.py` holds a `CliRunner` that copies the result surface of the Typer runner: `exit_code`, `stdout`, `stderr`, `output`, and `exception`. Two properties matter:

- It sets `COLUMNS=200` through an `os.environ` patch. Rich reads the live environment on each render. Without the pin, help panels wrap option names and substring assertions fail.
- Cyclopts turns every outcome into a `SystemExit`, including success, parse errors, and `--help`. The `except SystemExit` branch handles nearly every case. The `except BaseException` branch captures unhandled errors and does not re-raise them. This matches the Typer runner.

## Related

- [V1 installer boundary](../architecture/v1-installer-boundary.md) states the headless JSON and exit-code contract that the migration kept.
