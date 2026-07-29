"""Tests for TOML manifest validation and atomic persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from cheese_flow import desired_state as ds
from cheese_flow.desired_state import (
    ManifestError,
    default_config_path,
    load_desired_state,
    save_desired_state,
)
from cheese_flow.models import DEFAULT_MAX_DEPTH, DesiredState, RepositorySelection

VALID = """\
harnesses = ["claude-code", "codex", "cursor"]
components = ["hallouminate", "easy-cheese"]

[repositories]
search_roots = ["/home/me/Dev"]
max_depth = 2
selected = ["/home/me/Dev/project"]
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def load_error(tmp_path: Path, text: str) -> ManifestError:
    path = write(tmp_path, text)
    with pytest.raises(ManifestError) as excinfo:
        load_desired_state(path)
    assert excinfo.value.path == path
    assert str(path) in str(excinfo.value)
    return excinfo.value


# --- happy paths -----------------------------------------------------------


def test_loads_full_manifest(tmp_path: Path) -> None:
    state = load_desired_state(write(tmp_path, VALID))
    assert state == DesiredState(
        harnesses=("claude-code", "codex", "cursor"),
        components=("hallouminate", "easy-cheese"),
        repositories=RepositorySelection(
            search_roots=(Path("/home/me/Dev"),),
            max_depth=2,
            selected=(Path("/home/me/Dev/project"),),
        ),
    )


def test_repositories_table_is_optional(tmp_path: Path) -> None:
    state = load_desired_state(
        write(
            tmp_path,
            'harnesses = ["codex"]\ncomponents = ["hallouminate", "easy-cheese"]\n',
        )
    )
    assert state.repositories == RepositorySelection(
        search_roots=(), max_depth=DEFAULT_MAX_DEPTH, selected=()
    )


def test_empty_selected_is_valid(tmp_path: Path) -> None:
    state = load_desired_state(
        write(
            tmp_path,
            'harnesses = ["codex"]\n'
            'components = ["hallouminate", "easy-cheese"]\n'
            "[repositories]\n"
            'search_roots = ["/home/me/Dev"]\n'
            "selected = []\n",
        )
    )
    assert state.repositories.selected == ()
    assert state.repositories.max_depth == DEFAULT_MAX_DEPTH


def test_max_depth_zero_means_the_root_itself(tmp_path: Path) -> None:
    state = load_desired_state(
        write(
            tmp_path,
            'harnesses = ["codex"]\n'
            'components = ["hallouminate", "easy-cheese"]\n'
            "[repositories]\n"
            'search_roots = ["/home/me/Dev"]\n'
            "max_depth = 0\n",
        )
    )
    assert state.repositories.max_depth == 0


def test_optional_tilth_is_accepted(tmp_path: Path) -> None:
    state = load_desired_state(
        write(
            tmp_path,
            'harnesses = ["codex"]\ncomponents = ["hallouminate", "easy-cheese", "tilth"]\n',
        )
    )
    assert state.components == ("hallouminate", "easy-cheese", "tilth")


def test_selected_path_equal_to_search_root_is_consistent(tmp_path: Path) -> None:
    state = load_desired_state(
        write(
            tmp_path,
            'harnesses = ["codex"]\n'
            'components = ["hallouminate", "easy-cheese"]\n'
            "[repositories]\n"
            'search_roots = ["/home/me/Dev"]\n'
            'selected = ["/home/me/Dev"]\n',
        )
    )
    assert state.repositories.selected == (Path("/home/me/Dev"),)


# --- file and syntax errors ------------------------------------------------


def test_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    with pytest.raises(ManifestError) as excinfo:
        load_desired_state(path)
    assert excinfo.value.path == path
    assert "manifest not found" in excinfo.value.reason


def test_malformed_toml(tmp_path: Path) -> None:
    error = load_error(tmp_path, "harnesses = [\n")
    assert error.reason.startswith("invalid TOML:")


# --- unknown keys and names ------------------------------------------------


def test_unknown_top_level_key(tmp_path: Path) -> None:
    error = load_error(tmp_path, 'version = "1"\n' + VALID)
    assert error.reason == "unknown top-level keys: version"


def test_unknown_repositories_key(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID + "follow_symlinks = true\n")
    assert error.reason == "unknown keys in [repositories]: follow_symlinks"


def test_unknown_harness_name(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"codex"', '"pi"', 1))
    assert error.reason == "unknown harness names: pi (supported: claude-code, codex, cursor)"


def test_unknown_component_name(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"easy-cheese"', '"brie"', 1))
    assert error.reason == (
        "unknown component names: brie (supported: hallouminate, easy-cheese, tilth)"
    )


# --- wrong TOML types ------------------------------------------------------


def test_harnesses_must_be_an_array(tmp_path: Path) -> None:
    error = load_error(
        tmp_path, 'harnesses = "codex"\ncomponents = ["hallouminate", "easy-cheese"]\n'
    )
    assert error.reason == "harnesses must be an array of strings"


def test_search_roots_must_be_strings(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"/home/me/Dev"]', "1]", 1))
    assert error.reason == "search_roots must be an array of strings"


def test_repositories_must_be_a_table(tmp_path: Path) -> None:
    error = load_error(
        tmp_path,
        'harnesses = ["codex"]\ncomponents = ["hallouminate", "easy-cheese"]\nrepositories = 3\n',
    )
    assert error.reason == "repositories must be a table"


def test_max_depth_must_be_an_integer(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace("max_depth = 2", 'max_depth = "2"'))
    assert error.reason == "max_depth must be an integer"


def test_max_depth_rejects_booleans(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace("max_depth = 2", "max_depth = true"))
    assert error.reason == "max_depth must be an integer"


# --- missing keys ----------------------------------------------------------


def test_missing_harnesses(tmp_path: Path) -> None:
    error = load_error(tmp_path, 'components = ["hallouminate", "easy-cheese"]\n')
    assert error.reason == "missing required key: harnesses"


def test_missing_components(tmp_path: Path) -> None:
    error = load_error(tmp_path, 'harnesses = ["codex"]\n')
    assert error.reason == "missing required key: components"


# --- model invariants surfaced as ManifestError ----------------------------


def test_relative_search_root(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"/home/me/Dev"]', '"Dev"]', 1))
    assert "search_roots must be absolute paths: Dev" in error.reason


def test_relative_selected_path(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"/home/me/Dev/project"', '"project"'))
    assert "selected must be absolute paths: project" in error.reason


def test_duplicate_harnesses(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"cursor"', '"codex"'))
    assert "harnesses must not contain duplicates: codex" in error.reason


def test_duplicate_components(tmp_path: Path) -> None:
    error = load_error(
        tmp_path,
        VALID.replace(
            'components = ["hallouminate", "easy-cheese"]',
            'components = ["hallouminate", "easy-cheese", "hallouminate"]',
        ),
    )
    assert "components must not contain duplicates: hallouminate" in error.reason


def test_duplicate_search_roots(tmp_path: Path) -> None:
    error = load_error(
        tmp_path, VALID.replace('search_roots = ["/home/me/Dev"]', 'search_roots = ["/a", "/a"]')
    )
    assert "search_roots must not contain duplicates: /a" in error.reason


def test_duplicate_selected(tmp_path: Path) -> None:
    error = load_error(
        tmp_path,
        VALID.replace(
            'selected = ["/home/me/Dev/project"]',
            'selected = ["/home/me/Dev/p", "/home/me/Dev/p"]',
        ),
    )
    assert "selected must not contain duplicates: /home/me/Dev/p" in error.reason


def test_missing_required_component(tmp_path: Path) -> None:
    error = load_error(
        tmp_path,
        VALID.replace(
            'components = ["hallouminate", "easy-cheese"]', 'components = ["hallouminate"]'
        ),
    )
    assert "components must include required components: easy-cheese" in error.reason


def test_empty_harnesses(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('["claude-code", "codex", "cursor"]', "[]"))
    assert "harnesses must select at least one harness" in error.reason


def test_negative_max_depth(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace("max_depth = 2", "max_depth = -1"))
    assert "max_depth must be >= 0" in error.reason


# --- selection consistency -------------------------------------------------


def test_selected_outside_search_roots(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"/home/me/Dev/project"', '"/opt/other"'))
    assert error.reason == "selected repositories are not under any search root: /opt/other"


def test_selected_without_search_roots(tmp_path: Path) -> None:
    error = load_error(
        tmp_path,
        'harnesses = ["codex"]\n'
        'components = ["hallouminate", "easy-cheese"]\n'
        "[repositories]\n"
        'selected = ["/home/me/Dev/project"]\n',
    )
    assert error.reason == (
        "selected repositories are not under any search root: /home/me/Dev/project"
    )


def test_sibling_prefix_is_not_under_a_search_root(tmp_path: Path) -> None:
    error = load_error(tmp_path, VALID.replace('"/home/me/Dev/project"', '"/home/me/Development"'))
    assert (
        error.reason == "selected repositories are not under any search root: /home/me/Development"
    )


# --- persistence -----------------------------------------------------------


def test_round_trip(tmp_path: Path) -> None:
    state = DesiredState(
        harnesses=("claude-code", "cursor"),
        components=("hallouminate", "easy-cheese", "tilth"),
        repositories=RepositorySelection(
            search_roots=(Path("/home/me/Dev"), Path("/srv/code")),
            max_depth=0,
            selected=(Path("/home/me/Dev/a"), Path("/srv/code/b")),
        ),
    )
    path = tmp_path / "nested" / "config.toml"
    save_desired_state(state, path)
    assert load_desired_state(path) == state


def test_round_trip_with_empty_repository_selection(tmp_path: Path) -> None:
    state = DesiredState(harnesses=("codex",), components=("hallouminate", "easy-cheese"))
    path = tmp_path / "config.toml"
    save_desired_state(state, path)
    assert load_desired_state(path) == state


def test_save_creates_parent_directories(tmp_path: Path) -> None:
    state = DesiredState(harnesses=("codex",), components=("hallouminate", "easy-cheese"))
    path = tmp_path / "a" / "b" / "config.toml"
    save_desired_state(state, path)
    assert path.is_file()


def test_save_replaces_existing_manifest_and_leaves_no_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("harnesses = []\n", encoding="utf-8")
    state = DesiredState(harnesses=("codex",), components=("hallouminate", "easy-cheese"))
    save_desired_state(state, path)
    assert load_desired_state(path) == state
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_failed_serialization_leaves_the_existing_manifest_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write(tmp_path, VALID)
    state = DesiredState(harnesses=("codex",), components=("hallouminate", "easy-cheese"))

    def boom(_: DesiredState) -> str:
        raise RuntimeError("render failed")

    monkeypatch.setattr(ds, "_render_toml", boom)
    with pytest.raises(RuntimeError, match="render failed"):
        save_desired_state(state, path)

    assert path.read_text(encoding="utf-8") == VALID
    assert [p.name for p in tmp_path.iterdir()] == ["config.toml"]


def test_saved_manifest_matches_the_documented_shape(tmp_path: Path) -> None:
    state = DesiredState(
        harnesses=("claude-code", "codex", "cursor"),
        components=("hallouminate", "easy-cheese"),
        repositories=RepositorySelection(
            search_roots=(Path("/home/me/Dev"),),
            max_depth=2,
            selected=(Path("/home/me/Dev/project"),),
        ),
    )
    path = tmp_path / "config.toml"
    save_desired_state(state, path)
    assert path.read_text(encoding="utf-8") == VALID


# --- default config path ---------------------------------------------------


def test_default_config_path_uses_xdg_config_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    assert default_config_path() == Path("/xdg/cheese/config.toml")


def test_default_config_path_falls_back_to_home_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".config" / "cheese" / "config.toml"


def test_default_config_path_falls_back_when_xdg_is_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert default_config_path() == tmp_path / ".config" / "cheese" / "config.toml"


# --- symlinked search roots ------------------------------------------------


def _manifest(search_roots: list[Path], selected: list[Path]) -> str:
    return (
        'harnesses = ["claude-code"]\n'
        'components = ["hallouminate", "easy-cheese"]\n'
        "\n[repositories]\n"
        f"search_roots = {[str(p) for p in search_roots]}\n"
        "max_depth = 1\n"
        f"selected = {[str(p) for p in selected]}\n"
    ).replace("'", '"')


def test_symlinked_search_root_is_canonicalized_so_selections_stay_consistent(
    tmp_path: Path,
) -> None:
    real = (tmp_path / "data" / "Dev").resolve()
    real.mkdir(parents=True)
    link = tmp_path / "Dev"
    link.symlink_to(real)

    state = load_desired_state(write(tmp_path, _manifest([link], [real / "project"])))

    assert state.repositories.search_roots == (real,)
    assert state.repositories.selected == (real / "project",)


def test_nonexistent_search_root_is_kept_rather_than_dropped(tmp_path: Path) -> None:
    missing = tmp_path / "not-there"

    state = load_desired_state(write(tmp_path, _manifest([missing], [missing / "project"])))

    assert state.repositories.search_roots == (missing,)
    assert state.repositories.selected == (missing / "project",)


def test_selection_outside_every_search_root_is_still_rejected(tmp_path: Path) -> None:
    real = (tmp_path / "Dev").resolve()
    real.mkdir()

    error = load_error(tmp_path, _manifest([real], [tmp_path / "elsewhere"]))

    assert "not under any search root" in error.reason
