from __future__ import annotations

import json
from pathlib import Path

import cheese_flow.profiles.project_permissions as project_permissions_module
import pytest
from cheese_flow.profiles.errors import ProfilePermissionsError
from cheese_flow.profiles.models import ProjectPermissionsRequest
from cheese_flow.profiles.project_permissions import render_project_permissions


def _write_fragment(
    root: Path,
    *,
    allow: tuple[str, ...] = ("Bash(git:*)",),
    deny: tuple[str, ...] = (),
    extra: str = "",
) -> Path:
    fragment_dir = root / ".agent-profiles" / "_permissions"
    fragment_dir.mkdir(parents=True)
    lines = ["name: _permissions", "settings:"]
    if allow:
        lines.append("  permissions_allow:")
        lines.extend(f"    - {rule!r}" for rule in allow)
    if deny:
        lines.append("  permissions_deny:")
        lines.extend(f"    - {rule!r}" for rule in deny)
    if extra:
        lines.append(extra)
    fragment = fragment_dir / "profile.yaml"
    fragment.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return fragment


def test_default_harnesses_render_and_report_exact_paths(tmp_path: Path) -> None:
    _write_fragment(tmp_path)

    report = render_project_permissions(
        ProjectPermissionsRequest(project_root=tmp_path),
        environment={},
    )

    assert report.written == (
        tmp_path / ".claude" / "settings.json",
        tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules",
    )
    assert report.skipped_harnesses == ()
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text())["permissions"][
        "allow"
    ] == ["Bash(git:*)"]
    assert (tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules").is_file()


def test_local_mode_writes_claude_personal_settings_and_skips_codex(tmp_path: Path) -> None:
    _write_fragment(tmp_path, allow=("Edit",))

    report = render_project_permissions(
        ProjectPermissionsRequest(project_root=tmp_path, local=True),
        environment={},
    )

    assert report.written == (tmp_path / ".claude" / "settings.local.json",)
    assert report.skipped_harnesses == ("codex",)
    assert json.loads((tmp_path / ".claude" / "settings.local.json").read_text())["permissions"][
        "allow"
    ] == ["Edit"]
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert not (tmp_path / ".codex").exists()


def test_symlinked_claude_parent_is_rejected_before_any_write(tmp_path: Path) -> None:
    _write_fragment(tmp_path)
    redirect = tmp_path / "project" / "redirect"
    redirect.mkdir(parents=True)
    claude = tmp_path / ".claude"
    claude.symlink_to(redirect, target_is_directory=True)
    destination = claude / "settings.json"

    with pytest.raises(ProfilePermissionsError) as failure:
        render_project_permissions(
            ProjectPermissionsRequest(project_root=tmp_path, harnesses=("claude",)),
            environment={},
        )

    assert "must not be a symlink" in str(failure.value)
    assert str(destination) in str(failure.value)
    assert not (redirect / "settings.json").exists()


def test_codex_parent_substitution_is_rejected_in_final_atomic_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_fragment(tmp_path)
    redirect = tmp_path / "project" / "redirect"
    redirect.mkdir(parents=True)
    destination = tmp_path / ".codex" / "rules" / "cheese-flow-canonical.rules"
    real_atomic_replace = project_permissions_module._atomic_replace

    def substitute_parent(root: Path, path: Path, payload: bytes) -> None:
        assert path == destination
        codex = tmp_path / ".codex"
        codex.mkdir()
        (codex / "rules").symlink_to(redirect, target_is_directory=True)
        real_atomic_replace(root, path, payload)

    monkeypatch.setattr(
        project_permissions_module,
        "_atomic_replace",
        substitute_parent,
    )

    with pytest.raises(ProfilePermissionsError) as failure:
        render_project_permissions(
            ProjectPermissionsRequest(project_root=tmp_path, harnesses=("codex",)),
            environment={},
        )

    assert "must not be a symlink" in str(failure.value)
    assert str(destination) in str(failure.value)
    assert not (redirect / destination.name).exists()


def test_missing_fragment_fails_without_writes(tmp_path: Path) -> None:
    with pytest.raises(ProfilePermissionsError, match="profile.yaml"):
        render_project_permissions(
            ProjectPermissionsRequest(project_root=tmp_path),
            environment={},
        )

    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()


def test_top_level_permissions_without_nested_settings_fail_before_writes(
    tmp_path: Path,
) -> None:
    fragment_dir = tmp_path / ".agent-profiles" / "_permissions"
    fragment_dir.mkdir(parents=True)
    (fragment_dir / "profile.yaml").write_text(
        "name: _permissions\npermissions_allow:\n  - 'Bash(git:*)'\n",
        encoding="utf-8",
    )

    with pytest.raises(ProfilePermissionsError, match="settings"):
        render_project_permissions(
            ProjectPermissionsRequest(project_root=tmp_path),
            environment={},
        )

    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()


def test_unsupported_harness_fails_before_planning_or_writes(tmp_path: Path) -> None:
    _write_fragment(tmp_path)
    request = ProjectPermissionsRequest.model_construct(
        project_root=tmp_path,
        local=False,
        harnesses=("opencode",),
    )

    with pytest.raises(ProfilePermissionsError, match="opencode"):
        render_project_permissions(request, environment={})

    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".codex").exists()


def test_fragment_is_standalone_and_does_not_discover_other_profiles(tmp_path: Path) -> None:
    _write_fragment(tmp_path, allow=("Bash(project-only:*)",), extra="include: [global]")
    global_profile = tmp_path / "profiles" / "global"
    global_profile.mkdir(parents=True)
    (global_profile / "profile.yaml").write_text(
        "name: global\nsettings:\n  permissions_allow: [Bash(global:*)]\n",
        encoding="utf-8",
    )

    render_project_permissions(
        ProjectPermissionsRequest(project_root=tmp_path, harnesses=("claude",)),
        environment={},
    )

    permissions = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))[
        "permissions"
    ]
    assert permissions["allow"] == ["Bash(project-only:*)"]


def test_invalid_planned_destination_is_rejected_before_any_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_fragment(tmp_path)
    outside = tmp_path.parent / "outside-settings.json"
    safe = tmp_path / ".claude" / "settings.json"

    def plan_claude(profile, project_root, *, local):
        del profile, project_root, local
        return ((safe, b"safe"),)

    def plan_codex(profile, project_root, *, local):
        del profile, project_root, local
        return ((outside, b"escape"),)

    monkeypatch.setattr(
        "cheese_flow.profiles.project_permissions.plan_claude_project_permissions",
        plan_claude,
    )
    monkeypatch.setattr(
        "cheese_flow.profiles.project_permissions.plan_codex_project_permissions",
        plan_codex,
    )

    with pytest.raises(ProfilePermissionsError, match="project root"):
        render_project_permissions(
            ProjectPermissionsRequest(project_root=tmp_path),
            environment={},
        )

    assert not safe.exists()
    assert not outside.exists()
