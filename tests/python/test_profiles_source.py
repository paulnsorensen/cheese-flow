"""Behavioral tests for explicit profile-source introspection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cheese_flow.profiles.source import (
    ProfileSourceError,
    ResolvedProfile,
    list_profiles,
    load_profile,
)


def _profile(root: Path, name: str, text: str) -> Path:
    profile_dir = root / "profiles" / name
    profile_dir.mkdir(parents=True)
    (profile_dir / "profile.yaml").write_text(text, encoding="utf-8")
    return profile_dir


def _plugin_fixture(
    source_root: Path, *, source: str = "./", server_name: str = "plugin-server"
) -> Path:
    plugin_root = source_root / "plugins" / "marketplace"
    payload_root = plugin_root
    (payload_root / ".claude-plugin").mkdir(parents=True)
    (payload_root / "agents").mkdir()
    (payload_root / "skills" / "demo-skill").mkdir(parents=True)
    (payload_root / "hooks").mkdir()
    (payload_root / "agents" / "demo-agent.md").write_text(
        "---\nname: demo-agent\ndescription: Demo agent\n---\n# Agent\n",
        encoding="utf-8",
    )
    (payload_root / "skills" / "demo-skill" / "SKILL.md").write_text(
        "# Demo skill\n", encoding="utf-8"
    )
    (payload_root / "hooks" / "check.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (payload_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    server_name: {
                        "command": "demo-server",
                        "env": {"TOKEN": "${TOKEN}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (payload_root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "${CLAUDE_PLUGIN_ROOT}/hooks/check.sh",
                                }
                            ],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    (plugin_root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "local",
                "plugins": [{"name": "demo", "source": source}],
            }
        ),
        encoding="utf-8",
    )
    registry = source_root / "plugins" / "registry.yaml"
    registry.write_text(
        (
            "plugins:\n"
            "  demo:\n"
            "    git: https://example.com/demo.git\n"
            "    branch: main\n"
            "    path: plugins/marketplace\n"
            "    native: [claude]\n"
        ),
        encoding="utf-8",
    )
    return registry


def test_list_profiles_reads_only_the_explicit_source_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    other_root = tmp_path / "other"
    _profile(source_root, "local", "name: local\ndescription: Explicit\n")
    _profile(other_root, "foreign", "name: foreign\ndescription: Foreign\n")

    summaries = list_profiles(source_root)

    assert [(summary.name, summary.description, summary.source_id) for summary in summaries] == [
        ("local", "Explicit", "profiles/local")
    ]


def test_listed_profile_names_load_successfully(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "live", "name: live\ndescription: Live\n")

    summaries = list_profiles(source_root)
    assert [
        load_profile(source_root, summary.name, environment={}).name for summary in summaries
    ] == ["live"]


def test_profile_directory_and_manifest_identity_must_match(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "live", "name: other\n")

    with pytest.raises(ProfileSourceError, match="must match profile directory"):
        list_profiles(source_root)
    with pytest.raises(ProfileSourceError, match="must match profile directory"):
        load_profile(source_root, "live", environment={})


def test_listing_rejects_duplicate_canonical_profile_identities(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    profile_dir = _profile(source_root, "live", "name: live\n")
    (profile_dir.parent / "alias").symlink_to(profile_dir, target_is_directory=True)

    with pytest.raises(ProfileSourceError, match="duplicate profile identity"):
        list_profiles(source_root)


def test_codex_native_plugins_are_rejected_at_source_boundary(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    plugin_root = source_root / "plugins" / "codex-plugin"
    plugin_root.mkdir(parents=True)
    registry = source_root / "plugins" / "registry.yaml"
    registry.write_text(
        "plugins:\n  codex-plugin:\n    path: plugins/codex-plugin\n    native: [codex]\n",
        encoding="utf-8",
    )
    _profile(
        source_root,
        "live",
        "name: live\nregistries:\n  plugins: plugins/registry.yaml\n",
    )

    with pytest.raises(ProfileSourceError, match="codex-native"):
        load_profile(source_root, "live", environment={})


def test_load_profile_resolves_includes_and_declared_registries(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    registry = source_root / "agents" / "registry.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        "agents:\n  registered:\n    body_path: agents/registered.md\n", encoding="utf-8"
    )
    _profile(source_root, "base", "name: base\nregistries:\n  agents: agents/registry.yaml\n")
    _profile(
        source_root,
        "live",
        (
            "name: live\ninclude: [base]\ncompile_targets:\n"
            "  home:\n    target_root: $HOME\n    harnesses: [codex]\n"
        ),
    )

    profile = load_profile(source_root, "live", environment={"HOME": str(tmp_path / "home")})

    assert isinstance(profile, ResolvedProfile)
    assert profile.name == "live"
    assert profile.source_id == "profiles/live"
    assert [agent["name"] for agent in profile.agents] == ["registered"]
    assert profile.compile_targets[0].resolved_root == (tmp_path / "home").resolve()


def test_load_profile_normalizes_system_prompt_to_absolute_file(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    profile_dir = _profile(source_root, "codex", "name: codex\nsystem_prompt: AGENTS.md\n")
    prompt = profile_dir / "AGENTS.md"
    prompt.write_text("# Codex instructions\n", encoding="utf-8")

    profile = load_profile(source_root, "codex", environment={})

    assert profile.system_prompt == str(prompt.resolve())


def test_load_profile_rejects_missing_system_prompt(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "codex", "name: codex\nsystem_prompt: missing.md\n")

    with pytest.raises(ProfileSourceError, match="system_prompt is not a regular file"):
        load_profile(source_root, "codex", environment={})


def test_profile_name_traversal_is_rejected_before_reading_outside_root(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "profile.yaml"
    marker.write_text("name: outside\n", encoding="utf-8")
    (source_root / "profiles").mkdir(parents=True)

    with pytest.raises(ProfileSourceError, match="profile name"):
        load_profile(source_root, "../outside", environment={})

    assert marker.read_text(encoding="utf-8") == "name: outside\n"


def test_profile_symlink_escape_is_rejected_before_reading_target(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "profile.yaml").write_text("name: escaped\n", encoding="utf-8")
    (source_root / "profiles").mkdir(parents=True)
    (source_root / "profiles" / "escaped").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ProfileSourceError, match="escapes"):
        load_profile(source_root, "escaped", environment={})


def test_declared_registry_symlink_escape_is_rejected(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "registry.yaml").write_text("agents: {}\n", encoding="utf-8")
    (source_root / "agents").mkdir(parents=True)
    (source_root / "agents" / "registry.yaml").symlink_to(outside / "registry.yaml")
    _profile(
        source_root,
        "escaped",
        "name: escaped\nregistries:\n  agents: agents/registry.yaml\n",
    )

    with pytest.raises(ProfileSourceError, match="escapes"):
        load_profile(source_root, "escaped", environment={})


def test_nested_local_skills_registry_preserves_source_relative_path(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    skill_dir = source_root / "registries" / "skills" / "local" / "alpha"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Alpha\n", encoding="utf-8")
    _profile(
        source_root,
        "live",
        "name: live\nregistries:\n  skills: registries/skills/local\n",
    )

    profile = load_profile(source_root, "live", environment={})

    assert [{key: item[key] for key in ("name", "path")} for item in profile.skills] == [
        {"name": "alpha", "path": "registries/skills/local/alpha"}
    ]


def test_external_skill_registry_rejects_traversal_names(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    registry = source_root / "registries" / "skills.yaml"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        "sources:\n  example/repo:\n    skills: [../unsafe]\n",
        encoding="utf-8",
    )
    _profile(
        source_root,
        "live",
        "name: live\nregistries:\n  skills: registries/skills.yaml\n",
    )

    with pytest.raises(ProfileSourceError, match="invalid skills registry name"):
        load_profile(source_root, "live", environment={})


def test_include_cycles_fail_closed_before_recursive_merge(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "first", "name: first\ninclude: [second]\n")
    _profile(source_root, "second", "name: second\ninclude: [first]\n")

    with pytest.raises(ProfileSourceError, match="include cycle detected"):
        load_profile(source_root, "first", environment={})


def test_compile_target_rejects_unset_environment_reference(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(
        source_root,
        "live",
        "name: live\ncompile_targets:\n"
        "  home:\n    target_root: $MISSING_HOME\n    harnesses: [claude]\n",
    )

    with pytest.raises(ProfileSourceError, match="unset environment variable 'MISSING_HOME'"):
        load_profile(source_root, "live", environment={})


def test_compile_targets_reject_duplicate_harness_ownership(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(
        source_root,
        "live",
        "name: live\ncompile_targets:\n"
        "  first:\n    target_root: $FIRST\n    harnesses: [claude]\n"
        "  second:\n    target_root: $SECOND\n    harnesses: [claude]\n",
    )

    with pytest.raises(ProfileSourceError, match="duplicates harness 'claude'"):
        load_profile(
            source_root,
            "live",
            environment={"FIRST": str(tmp_path / "first"), "SECOND": str(tmp_path / "second")},
        )


def test_profile_item_path_traversal_is_rejected_during_source_loading(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(
        source_root,
        "live",
        "name: live\nagents:\n  - name: helper\n    body_path: ../outside.md\n",
    )

    with pytest.raises(ProfileSourceError, match="body_path"):
        load_profile(source_root, "live", environment={})


def test_load_profile_requires_an_explicit_environment_keyword(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "codex", "name: codex\n")

    with pytest.raises(TypeError):
        load_profile(source_root, "codex")


def test_duplicate_items_across_includes_are_rejected_with_context(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "base", "name: base\nagents:\n  - name: shared\n")
    _profile(
        source_root,
        "live",
        "name: live\ninclude: [base]\nagents:\n  - name: shared\n",
    )

    with pytest.raises(ProfileSourceError, match="duplicate agents item name 'shared'.*conflicts"):
        load_profile(source_root, "live", environment={})


def test_duplicate_items_across_declared_registries_are_rejected(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    agents_dir = source_root / "agents"
    agents_dir.mkdir(parents=True)
    for filename in ("one.yaml", "two.yaml"):
        (agents_dir / filename).write_text(
            "agents:\n  shared:\n    body_path: agents/shared.md\n",
            encoding="utf-8",
        )
    _profile(
        source_root,
        "live",
        "name: live\nregistries:\n  agents: [agents/one.yaml, agents/two.yaml]\n",
    )

    with pytest.raises(ProfileSourceError, match="duplicate agents item name 'shared'.*conflicts"):
        load_profile(source_root, "live", environment={})


def test_duplicate_yaml_mapping_keys_fail_during_source_load(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    agents_dir = source_root / "agents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "registry.yaml").write_text(
        "agents:\n  shared: {}\n  shared: {}\n",
        encoding="utf-8",
    )
    _profile(source_root, "live", "name: live\nregistries:\n  agents: agents/registry.yaml\n")

    with pytest.raises(ProfileSourceError, match="duplicate key"):
        load_profile(source_root, "live", environment={})


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("isolated", '"yes"'),
        ("tools", "Read"),
        ("enabled_plugins", "plugin"),
        ("env", "HOME"),
        ("marketplaces", "claude"),
    ),
)
def test_malformed_source_scalars_are_rejected(tmp_path: Path, field: str, value: str) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "live", f"name: live\n{field}: {value}\n")

    with pytest.raises(ProfileSourceError, match=field):
        load_profile(source_root, "live", environment={})


def test_list_fields_require_sequences_of_strings(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "live", "name: live\ntools: [Read, 1]\n")

    with pytest.raises(ProfileSourceError, match="tools"):
        load_profile(source_root, "live", environment={})


def test_marketplaces_are_immutable_snapshots(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "live", "name: live\nmarketplaces:\n  local: /plugins\n")

    profile = load_profile(source_root, "live", environment={})

    with pytest.raises(TypeError):
        profile.marketplaces["local"] = "/other"  # type: ignore[index]


def test_item_harnesses_require_an_explicit_string_sequence(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(
        source_root,
        "live",
        "name: live\nagents:\n  - name: helper\n    harnesses: claude\n",
    )

    with pytest.raises(ProfileSourceError, match="harnesses"):
        load_profile(source_root, "live", environment={})


def test_declared_environment_resolves_explicit_caller_values_without_leaking_raw_env(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _profile(
        source_root,
        "live",
        (
            "name: live\n"
            "env:\n"
            "  caller_value: '{{ env \"TOKEN\" }}'\n"
            "  caller_source_value: '${SOURCE_ONLY}'\n"
            "compile_targets:\n"
            "  home:\n"
            "    target_root: $TARGET_ROOT\n"
            "    harnesses: [claude]\n"
        ),
    )

    raw_secret = "raw-caller-secret"
    profile = load_profile(
        source_root,
        "live",
        environment={
            "TOKEN": "from-caller",
            "SOURCE_ONLY": "local",
            "TARGET_ROOT": str(tmp_path / "target"),
            "UNDECLARED_SECRET": raw_secret,
        },
    )

    assert dict(profile.env) == {
        "caller_value": "from-caller",
        "caller_source_value": "local",
    }
    assert profile.template_environment["TOKEN"] == "from-caller"
    assert profile.template_environment["SOURCE_ONLY"] == "local"
    assert profile.template_environment["UNDECLARED_SECRET"] == raw_secret

    assert "UNDECLARED_SECRET" not in profile.model_dump()
    assert raw_secret not in repr(profile)


def test_template_environment_is_private_but_available_to_renderers(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    _profile(
        source_root,
        "live",
        ("name: live\nmcps:\n  - name: templated\n    command: '{{ env \"TOKEN\" }}'\n"),
    )

    secret = "caller-secret"
    profile = load_profile(source_root, "live", environment={"TOKEN": secret})

    assert profile.mcps[0]["command"] == '{{ env "TOKEN" }}'
    assert profile.template_environment["TOKEN"] == secret
    assert "TOKEN" not in profile.model_dump()
    assert secret not in repr(profile)


def test_unknown_profile_and_compile_target_keys_fail_closed(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _profile(source_root, "typo", "name: typo\nisolatd: true\n")

    with pytest.raises(ProfileSourceError, match="isolatd"):
        load_profile(source_root, "typo", environment={})

    _profile(
        source_root,
        "nested",
        (
            "name: nested\ncompile_targets:\n"
            "  home:\n"
            "    target_root: /tmp/home\n"
            "    harnesses: [claude]\n"
            "    isolatd: true\n"
        ),
    )
    with pytest.raises(ProfileSourceError, match="isolatd"):
        load_profile(source_root, "nested", environment={})


def test_declared_plugins_decompose_native_and_non_native_primitives(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    registry = _plugin_fixture(source_root)
    _profile(
        source_root,
        "live",
        ("name: live\nregistries:\n  plugins: plugins/registry.yaml\n"),
    )

    profile = load_profile(source_root, "live", environment={"TOKEN": "caller-secret"})

    assert [item["name"] for item in profile.mcps] == ["plugin-server"]
    assert profile.mcps[0]["env"] == {"TOKEN": "${TOKEN}"}
    assert profile.mcps[0]["_from_native_plugin"] is True
    assert [item["name"] for item in profile.agents] == ["demo-agent"]
    assert "opencode" in profile.agents[0]["harnesses"]
    assert [item["name"] for item in profile.skills] == ["demo-skill"]
    assert profile.skills[0]["_from_native_plugin"] is True
    assert profile.hooks[0]["script"] == "hooks/check.sh"
    assert "codex" in profile.hooks[0]["harnesses"]
    assert dict(profile.native_plugins[0]) == {
        "name": "demo",
        "claude_native": True,
        "codex_native": False,
        "copilot_native": False,
        "servers": ("plugin-server",),
        "marketplace_root": str((source_root / "plugins" / "marketplace").resolve()),
        "marketplace_name": "local",
        "description": "",
        "_source_context": f"{registry}:plugins['demo']",
    }


def test_git_plugins_use_prepared_cheese_flow_cache(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    registry = _plugin_fixture(source_root)
    home = tmp_path / "home"
    cached_plugin = home / ".cache" / "cheese-flow" / "plugins" / "demo"
    cached_plugin.parent.mkdir(parents=True)
    (source_root / "plugins" / "marketplace").rename(cached_plugin)
    registry.write_text(
        (
            "plugins:\n"
            "  demo:\n"
            "    git: https://example.com/demo.git\n"
            "    branch: main\n"
            "    native: true\n"
        ),
        encoding="utf-8",
    )
    _profile(
        source_root,
        "live",
        "name: live\nregistries:\n  plugins: plugins/registry.yaml\n",
    )

    profile = load_profile(
        source_root,
        "live",
        environment={"HOME": str(home), "TOKEN": "caller-secret"},
    )

    assert profile.native_plugins[0]["marketplace_root"] == str(cached_plugin.resolve())
    assert profile.native_plugins[0]["claude_native"] is True
    assert profile.native_plugins[0]["codex_native"] is False
    assert profile.native_plugins[0]["copilot_native"] is True
    assert [item["name"] for item in profile.skills] == ["demo-skill"]
    assert profile.model_dump(mode="json")["native_plugins"][0]["marketplace_root"] == str(
        cached_plugin.resolve()
    )


def test_plugin_payload_traversal_is_rejected(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _plugin_fixture(source_root, source="../outside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / ".claude-plugin").mkdir()
    (outside / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
    _profile(
        source_root,
        "live",
        "name: live\nregistries:\n  plugins: plugins/registry.yaml\n",
    )

    with pytest.raises(ProfileSourceError, match="relative"):
        load_profile(source_root, "live", environment={})


def test_plugin_primitives_collide_with_explicit_items(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    _plugin_fixture(source_root, server_name="shared")
    _profile(
        source_root,
        "live",
        (
            "name: live\n"
            "registries:\n"
            "  plugins: plugins/registry.yaml\n"
            "mcps:\n"
            "  - name: shared\n"
            "    command: explicit\n"
        ),
    )

    with pytest.raises(ProfileSourceError, match="duplicate mcps item name 'shared'"):
        load_profile(source_root, "live", environment={"TOKEN": "caller-secret"})


def test_source_apis_ignore_legacy_ambient_discovery_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "explicit-source"
    _profile(source_root, "live", "name: live\ndescription: explicit\n")

    ambient_roots = {
        "DOTFILES_DIR": tmp_path / "dotfiles-decoy",
        "HOME": tmp_path / "home-decoy",
        "XDG_CONFIG_HOME": tmp_path / "xdg-config-decoy",
        "XDG_CACHE_HOME": tmp_path / "xdg-cache-decoy",
        "XDG_DATA_HOME": tmp_path / "xdg-data-decoy",
        "XDG_STATE_HOME": tmp_path / "xdg-state-decoy",
    }
    for root in ambient_roots.values():
        _profile(root, "live", "name: live\ndescription: ambient decoy\n")

    cwd = tmp_path / "cwd-decoy"
    cwd.mkdir()
    _profile(cwd, "live", "name: live\ndescription: cwd decoy\n")
    (cwd / ".env").write_text("DOTFILES_DIR=/wrong/source\n", encoding="utf-8")
    for directory in (".cache", ".vault"):
        _profile(cwd / directory, "live", "name: live\ndescription: hidden decoy\n")
    monkeypatch.chdir(cwd)
    for variable, root in ambient_roots.items():
        monkeypatch.setenv(variable, str(root))

    summaries = list_profiles(source_root)
    assert [(summary.name, summary.description, summary.source_id) for summary in summaries] == [
        ("live", "explicit", "profiles/live")
    ]

    profile = load_profile(source_root, "live", environment={})
    assert profile.description == "explicit"
