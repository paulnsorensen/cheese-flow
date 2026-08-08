from __future__ import annotations

import json
from pathlib import Path

import pytest
from cheese_flow.profiles.errors import ProfilePermissionsError
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.project_permissions_claude import plan_project_permissions


def _profile(*, allow: tuple[str, ...] = (), deny: tuple[str, ...] = ()) -> ResolvedProfile:
    return ResolvedProfile(
        name="project-permissions",
        source_id="profiles/project-permissions",
        settings={"permissions_allow": allow, "permissions_deny": deny},
    )


def _planned_json(planned: tuple[tuple[Path, bytes], ...]) -> dict[str, object]:
    assert len(planned) == 1
    return json.loads(planned[0][1].decode("utf-8"))


def test_committed_plan_updates_only_claude_permissions(tmp_path: Path) -> None:
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    original = {
        "permissions": {
            "allow": ["old"],
            "deny": ["old-deny"],
            "defaultMode": "allow",
        },
        "enabledPlugins": {"project-plugin": True},
    }
    settings_path.write_text(json.dumps(original) + "\n", encoding="utf-8")

    planned = plan_project_permissions(
        _profile(allow=("Bash(git status:*)", "Edit"), deny=("Grep",)),
        tmp_path,
        local=False,
    )

    assert planned[0][0] == settings_path
    assert json.loads(settings_path.read_text(encoding="utf-8")) == original
    assert _planned_json(planned) == {
        "permissions": {
            "allow": ["Bash(git status:*)", "Edit"],
            "deny": ["Grep"],
            "defaultMode": "allow",
        },
        "enabledPlugins": {"project-plugin": True},
    }


def test_local_plan_targets_personal_settings_and_preserves_portable_split(
    tmp_path: Path,
) -> None:
    portable_path = tmp_path / ".claude" / "settings.json"
    local_path = tmp_path / ".claude" / "settings.local.json"
    portable_path.parent.mkdir(parents=True)
    portable = {"permissions": {"allow": ["portable"]}, "enabledPlugins": {"portable": True}}
    local = {"permissions": {"allow": ["old-local"]}, "theme": "dark"}
    portable_path.write_text(json.dumps(portable) + "\n", encoding="utf-8")
    local_path.write_text(json.dumps(local) + "\n", encoding="utf-8")

    planned = plan_project_permissions(
        _profile(allow=("Read",), deny=()),
        tmp_path,
        local=True,
    )

    assert planned[0][0] == local_path
    assert json.loads(portable_path.read_text(encoding="utf-8")) == portable
    assert json.loads(local_path.read_text(encoding="utf-8")) == local
    assert _planned_json(planned) == {
        "permissions": {"allow": ["Read"], "deny": []},
        "theme": "dark",
    }


def test_plan_bootstraps_missing_settings_without_writing(tmp_path: Path) -> None:
    planned = plan_project_permissions(_profile(allow=("Read",)), tmp_path, local=False)

    assert planned[0][0] == tmp_path / ".claude" / "settings.json"
    assert not (tmp_path / ".claude").exists()
    assert _planned_json(planned) == {"permissions": {"allow": ["Read"], "deny": []}}


def test_plan_rejects_malformed_existing_settings_before_returning_bytes(tmp_path: Path) -> None:
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(ProfilePermissionsError, match="JSON object"):
        plan_project_permissions(_profile(allow=("Read",)), tmp_path, local=False)
