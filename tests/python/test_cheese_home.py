"""Tests for `python/cheese_flow/lib/cheese_home.py`.

Line-by-line port of `tests/cheese-home.test.ts`. Each describe block
maps to a sibling pytest test cluster; each `it(...)` maps to one
`def test_...` function.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from cheese_flow.lib.cheese_home import (
    CheeseHomeOptions,
    discover_canonical_repo,
    ensure_cheese_home,
    parse_worktree_main,
    path_slug,
    read_retention_config,
    resolve_cheese_home,
)

GIT_ENV = {
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _init_real_repo(directory: Path) -> None:
    subprocess.run(
        ["git", "init", "--quiet", "-b", "main", str(directory)],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(directory),
            "commit",
            "--allow-empty",
            "-m",
            "init",
            "--quiet",
        ],
        check=True,
        env={**os.environ, **GIT_ENV},
    )


# ---------- pathSlug ----------


def test_path_slug_replaces_every_slash_with_dash() -> None:
    assert path_slug("/Users/paul/Dev/cheese-flow") == "-Users-paul-Dev-cheese-flow"


def test_path_slug_returns_dash_for_filesystem_root() -> None:
    assert path_slug("/") == "-"


def test_path_slug_preserves_trailing_slash_as_trailing_dash() -> None:
    assert path_slug("/Users/paul/Dev/cheese-flow/") == "-Users-paul-Dev-cheese-flow-"


def test_path_slug_does_not_escape_legitimate_dash_in_segments() -> None:
    assert path_slug("/Users/john-doe/Dev/cheese-flow") == "-Users-john-doe-Dev-cheese-flow"


def test_path_slug_returns_input_unchanged_when_no_slash() -> None:
    assert path_slug("plain-name") == "plain-name"


# ---------- discoverCanonicalRepo ----------


def test_discover_canonical_repo_returns_canonical_absolute_path_for_plain_checkout(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "plain"
    repo.mkdir()
    _init_real_repo(repo)
    assert discover_canonical_repo(str(repo)) == str(repo.resolve())


def test_discover_canonical_repo_returns_main_worktree_path_from_linked_worktree(
    tmp_path: Path,
) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _init_real_repo(main)
    linked = tmp_path / "main-linked"
    subprocess.run(
        [
            "git",
            "-C",
            str(main),
            "worktree",
            "add",
            "-b",
            "feature",
            str(linked),
        ],
        check=True,
        env={**os.environ, **GIT_ENV},
    )
    assert discover_canonical_repo(str(linked)) == str(main.resolve())


def test_discover_canonical_repo_throws_when_cwd_not_inside_git_repo(
    tmp_path: Path,
) -> None:
    nogit = tmp_path / "nogit"
    nogit.mkdir()
    with pytest.raises(RuntimeError, match=r"not inside a git"):
        discover_canonical_repo(str(nogit))


# ---------- parseWorktreeMain ----------


def test_parse_worktree_main_returns_path_from_first_worktree_line() -> None:
    out = "worktree /repos/main\nbranch refs/heads/main\nHEAD abc\n"
    assert parse_worktree_main(out, "/cwd") == "/repos/main"


def test_parse_worktree_main_throws_when_porcelain_output_empty() -> None:
    with pytest.raises(RuntimeError, match=r"not inside a git"):
        parse_worktree_main("", "/cwd")


def test_parse_worktree_main_throws_when_first_line_not_worktree_marker() -> None:
    with pytest.raises(RuntimeError, match=r"not inside a git"):
        parse_worktree_main("HEAD abc\n", "/cwd")


# ---------- resolveCheeseHome — explicit canonicalRepo ----------


def test_resolve_cheese_home_skips_git_lookup_when_canonical_repo_provided(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    canonical_repo = "/Users/paul/Dev/example-repo"

    paths = resolve_cheese_home(
        str(cwd),
        CheeseHomeOptions(home=str(home), canonicalRepo=canonical_repo),
    )

    assert paths.projectDir == os.path.join(str(home), "projects", path_slug(canonical_repo))


# ---------- resolveCheeseHome ----------


def test_resolve_cheese_home_derives_all_paths_from_cwd_without_writing(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _init_real_repo(cwd)
    home = tmp_path / "home"
    home.mkdir()

    paths = resolve_cheese_home(str(cwd), CheeseHomeOptions(home=str(home)))

    real_cwd = str(cwd.resolve())
    repo_slug = path_slug(real_cwd)
    wt_slug = path_slug(real_cwd)
    assert paths.root == str(home)
    assert paths.projectDir == os.path.join(str(home), "projects", repo_slug)
    assert paths.milknadoDb == os.path.join(
        str(home), "projects", repo_slug, "milknado", "milknado.db"
    )
    assert paths.worktreeDir == os.path.join(str(home), "projects", repo_slug, "worktrees", wt_slug)
    assert paths.manifestsDir == os.path.join(
        str(home), "projects", repo_slug, "worktrees", wt_slug, "manifests"
    )
    assert paths.runsDir == os.path.join(
        str(home), "projects", repo_slug, "worktrees", wt_slug, "runs"
    )
    assert paths.sharedDir == os.path.join(str(home), "projects", repo_slug, "shared")

    assert not Path(str(home), "projects", repo_slug, "milknado", "milknado.db").exists()


def test_resolve_cheese_home_uses_homedir_when_no_override(tmp_path: Path) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _init_real_repo(cwd)

    paths = resolve_cheese_home(str(cwd))
    assert paths.root == str(Path.home() / ".cheese")


# ---------- ensureCheeseHome ----------


def test_ensure_cheese_home_creates_tree_and_writes_path_sidecar(
    tmp_path: Path,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _init_real_repo(cwd)
    home = tmp_path / "home"
    home.mkdir()

    paths = ensure_cheese_home(str(cwd), CheeseHomeOptions(home=str(home)))

    assert Path(paths.projectDir).is_dir()
    assert Path(paths.milknadoDb).parent.is_dir()
    assert Path(paths.manifestsDir).is_dir()
    assert Path(paths.runsDir).is_dir()
    assert Path(paths.sharedDir).is_dir()

    sidecar_path = Path(paths.worktreeDir, ".path")
    sidecar = sidecar_path.read_text(encoding="utf-8")
    assert sidecar == f"{cwd.resolve()}\n"


def test_ensure_cheese_home_is_idempotent(tmp_path: Path) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    _init_real_repo(cwd)
    home = tmp_path / "home"
    home.mkdir()

    first = ensure_cheese_home(str(cwd), CheeseHomeOptions(home=str(home)))
    second = ensure_cheese_home(str(cwd), CheeseHomeOptions(home=str(home)))

    assert second.worktreeDir == first.worktreeDir
    sidecar = Path(first.worktreeDir, ".path").read_text(encoding="utf-8")
    assert sidecar == f"{cwd.resolve()}\n"


# ---------- readRetentionConfig ----------


def test_read_retention_config_returns_default_when_no_toml(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    config = read_retention_config(str(project_dir))

    assert config.defaultDays == 30
    assert config.milknadoDays is None
    assert config.manifestsDays is None
    assert config.runsDays is None
    assert config.worktreeDays is None


def test_read_retention_config_reads_numeric_overrides(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "shared").mkdir(parents=True)
    (project_dir / "shared" / "retention.toml").write_text(
        "\n".join(
            [
                "defaultDays = 14",
                "milknadoDays = 7",
                "manifestsDays = 3",
                "runsDays = 90",
                "worktreeDays = 60",
            ]
        ),
        encoding="utf-8",
    )

    config = read_retention_config(str(project_dir))

    assert config.defaultDays == 14
    assert config.milknadoDays == 7
    assert config.manifestsDays == 3
    assert config.runsDays == 90
    assert config.worktreeDays == 60


def test_read_retention_config_ignores_section_headers_and_non_numeric_values(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "shared").mkdir(parents=True)
    (project_dir / "shared" / "retention.toml").write_text(
        "\n".join(
            [
                "[retention]",
                "no-equals-sign-here",
                "milknadoDays = not-a-number",
                "manifestsDays =",
                "runsDays = 12",
            ]
        ),
        encoding="utf-8",
    )

    config = read_retention_config(str(project_dir))

    assert config.defaultDays == 30
    assert config.milknadoDays is None
    assert config.manifestsDays is None
    assert config.runsDays == 12


def test_read_retention_config_ignores_comments_blank_lines_and_unknown_keys(
    tmp_path: Path,
) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "shared").mkdir(parents=True)
    (project_dir / "shared" / "retention.toml").write_text(
        "\n".join(
            [
                "# retention overrides",
                "",
                "defaultDays = 21",
                "unknownKey = 99",
                "  milknadoDays = 5  # inline ignored",
            ]
        ),
        encoding="utf-8",
    )

    config = read_retention_config(str(project_dir))

    assert config.defaultDays == 21
    assert config.milknadoDays == 5
    assert not hasattr(config, "unknownKey")
