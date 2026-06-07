"""Port of `src/lib/cheese-home.ts` — ``~/.cheese`` home directory resolution.

Mirrors the TS surface: ``CheeseHomePaths``, ``CheeseHomeOptions``,
``RetentionConfig``, ``path_slug``, ``discover_canonical_repo``,
``parse_worktree_main``, ``resolve_cheese_home``, ``ensure_cheese_home``,
and ``read_retention_config``.

Field names on the dataclasses keep TS camelCase (``projectDir``,
``milknadoDb``, etc.) so callers ported from TS read the same.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEFAULT_RETENTION_DAYS = 30
_RETENTION_NUMERIC_KEYS: frozenset[str] = frozenset(
    {
        "defaultDays",
        "milknadoDays",
        "manifestsDays",
        "runsDays",
        "worktreeDays",
    }
)


@dataclass(frozen=True)
class CheeseHomePaths:
    root: str
    projectDir: str
    milknadoDb: str
    worktreeDir: str
    manifestsDir: str
    runsDir: str
    sharedDir: str


@dataclass(frozen=True)
class CheeseHomeOptions:
    home: str | None = None
    canonicalRepo: str | None = None


@dataclass
class RetentionConfig:
    defaultDays: int = DEFAULT_RETENTION_DAYS
    milknadoDays: int | None = None
    manifestsDays: int | None = None
    runsDays: int | None = None
    worktreeDays: int | None = None


def path_slug(abs_path: str) -> str:
    return abs_path.replace("/", "-")


def parse_worktree_main(out: str, cwd: str) -> str:
    first_line = out.split("\n", 1)[0] if out else ""
    if not first_line.startswith("worktree "):
        raise RuntimeError(
            f"discoverCanonicalRepo: {cwd} is not inside a git worktree (no 'worktree' line)"
        )
    return first_line[len("worktree ") :]


def _run_git_worktree_list(cwd: str) -> str:
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        message = str(error)
        raise RuntimeError(
            f"discoverCanonicalRepo: {cwd} is not inside a git repo: {message}"
        ) from error
    return result.stdout


def discover_canonical_repo(cwd: str) -> str:
    out = _run_git_worktree_list(cwd)
    return str(Path(parse_worktree_main(out, cwd)).resolve())


def resolve_cheese_home(cwd: str, options: CheeseHomeOptions | None = None) -> CheeseHomePaths:
    opts = options or CheeseHomeOptions()
    root = opts.home if opts.home is not None else str(Path.home() / ".cheese")
    canonical_repo = (
        opts.canonicalRepo if opts.canonicalRepo is not None else discover_canonical_repo(cwd)
    )
    repo_slug = path_slug(canonical_repo)
    worktree_path = str(Path(cwd).resolve())
    wt_slug = path_slug(worktree_path)
    project_dir = os.path.join(root, "projects", repo_slug)
    worktree_dir = os.path.join(project_dir, "worktrees", wt_slug)
    return CheeseHomePaths(
        root=root,
        projectDir=project_dir,
        milknadoDb=os.path.join(project_dir, "milknado", "milknado.db"),
        worktreeDir=worktree_dir,
        manifestsDir=os.path.join(worktree_dir, "manifests"),
        runsDir=os.path.join(worktree_dir, "runs"),
        sharedDir=os.path.join(project_dir, "shared"),
    )


def ensure_cheese_home(cwd: str, options: CheeseHomeOptions | None = None) -> CheeseHomePaths:
    paths = resolve_cheese_home(cwd, options)
    os.makedirs(os.path.dirname(paths.milknadoDb), exist_ok=True)
    os.makedirs(paths.manifestsDir, exist_ok=True)
    os.makedirs(paths.runsDir, exist_ok=True)
    os.makedirs(paths.sharedDir, exist_ok=True)
    _write_sidecar(paths.worktreeDir, str(Path(cwd).resolve()))
    return paths


def _write_sidecar(worktree_dir: str, original_path: str) -> None:
    Path(worktree_dir, ".path").write_text(f"{original_path}\n", encoding="utf-8")


def read_retention_config(project_dir: str) -> RetentionConfig:
    toml_path = Path(project_dir) / "shared" / "retention.toml"
    try:
        body = toml_path.read_text(encoding="utf-8")
    except OSError:
        return RetentionConfig()
    return _parse_retention_toml(body)


def _strip_comment(line: str) -> str:
    hash_idx = line.find("#")
    return line if hash_idx < 0 else line[:hash_idx]


def _parse_retention_toml(body: str) -> RetentionConfig:
    config: dict[str, int] = {"defaultDays": DEFAULT_RETENTION_DAYS}
    for raw_line in body.splitlines():
        line = _strip_comment(raw_line).strip()
        if line == "" or line.startswith("["):
            continue
        eq = line.find("=")
        if eq < 0:
            continue
        key = line[:eq].strip()
        value = line[eq + 1 :].strip()
        if key not in _RETENTION_NUMERIC_KEYS:
            continue
        try:
            parsed = int(value, 10)
        except ValueError:
            continue
        config[key] = parsed
    return RetentionConfig(
        defaultDays=config.get("defaultDays", DEFAULT_RETENTION_DAYS),
        milknadoDays=config.get("milknadoDays"),
        manifestsDays=config.get("manifestsDays"),
        runsDays=config.get("runsDays"),
        worktreeDays=config.get("worktreeDays"),
    )
