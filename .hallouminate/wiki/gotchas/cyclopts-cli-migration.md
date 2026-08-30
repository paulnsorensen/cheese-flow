# cyclopts replaced typer — three behaviors don't survive a naive port

PR #112 swapped the `cheese` root app and the `profile` subapp from typer to cyclopts.
The framework has no drop-in shim, so three call sites carry deliberate,
easy-to-regress workarounds rather than a like-for-like translation.[^1]

## `negative=""` must be set on every boolean/list option, or cyclopts adds an unwanted flag

Cyclopts auto-generates a `--no-<flag>` negation for every boolean `Parameter` and an
`--empty-<name>` clearing flag for every list `Parameter`. Typer has no equivalent, so
none of the ported options wanted one. Every affected `Parameter(...)` in `cli.py`
explicitly passes `negative=""` to suppress it — omitting that on a newly added
boolean or list option silently reintroduces an undocumented flag into `--help` and
the parser, rather than failing loudly.

## `typer.Exit(code)` becomes `raise SystemExit(code)` — the exit-code contract is unchanged, the call shape is not

Cyclopts has no `Exit` exception; the migration replaces every `typer.Exit(n)` with
`raise SystemExit(n)`. The exit-code contract itself is preserved exactly (`0`
success, `1` failure, `2` manifest/option errors — see the `_FAILURE_EXIT_CODE` /
`_MANIFEST_EXIT_CODE` call sites), so this is a mechanical rename, but grepping for
`typer.Exit` to find remaining call sites after this PR will find nothing — the
pattern to grep for is `raise SystemExit`.

## Passthrough launch args use a variadic `Parameter`, not a typer `Context`

`profiles/cli.py`'s `launch` command forwards arbitrary harness arguments. Typer did
this by taking a `Context` and reading `ctx.args`. Cyclopts has no equivalent context
object for this; the port uses `*arguments: Annotated[tuple[str, ...], Parameter(allow_leading_hyphen=True)]`
so leading-hyphen tokens (`--foo`, `-x`) are captured as forwarded arguments instead of
being parsed as options of the `launch` command itself — with or without a `--`
separator ahead of them.

## Cyclopts ships no test runner — `tests/python/cyclopts_testing.py` is hand-rolled

Typer's `CliRunner` has no cyclopts counterpart. `cyclopts_testing.CliRunner` is a
from-scratch wrapper shaped to match Typer's `CliRunner` result surface
(`exit_code`/`stdout`/`stderr`/`output`/`exception`) so the already-migrated test
assertions didn't need rewriting. It has two properties worth knowing before touching
it:

- It pins `COLUMNS=200` via `os.environ` patching, because Rich reads the live
  environment on every render to decide help-panel wrap width — a live reference, not
  a snapshot, so `mock.patch.dict` is what reaches it. Removing that pin reintroduces
  wrapped option names that break substring assertions in help-output tests.
- Cyclopts turns every outcome — success, parse error, `--help` — into a `SystemExit`.
  The runner's `try/except SystemExit` is therefore the only path that ever fires in
  practice; the `except BaseException` fallback exists for genuinely unhandled errors
  and deliberately mirrors Typer's `CliRunner` by capturing rather than re-raising.

## Related

- [V1 installer boundary](../architecture/v1-installer-boundary.md) — the headless
  JSON/exit-code contract this migration preserved.

[^1]: `python/cheese_flow/cli.py` (`negative=""` Parameter sites, `SystemExit` call
sites); `python/cheese_flow/profiles/cli.py:174-177` (`launch` variadic passthrough);
`tests/python/cyclopts_testing.py` (the hand-rolled `CliRunner`). Introduced by commit
`68f08d5` ("refactor(cli): migrate the cheese CLI from typer to cyclopts (#112)").
