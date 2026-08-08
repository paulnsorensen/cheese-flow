"""Behavioral tests for private profile compilation and publication."""

from __future__ import annotations

import importlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath

import pytest
from cheese_flow.profiles.apply import apply_profile
from cheese_flow.profiles.drift import DriftError, FileComparison, compute_drift
from cheese_flow.profiles.errors import ProfileCompileError
from cheese_flow.profiles.manifest_codec import load_manifest
from cheese_flow.profiles.models import CompileRequest

compile_module = importlib.import_module("cheese_flow.profiles.compile")


class _FailingRenderer:
    name = "claude"

    def render(self, profile, target: Path, *, logical_root: Path):
        del profile, target, logical_root
        raise RuntimeError("renderer failed")


class _Renderer:
    name = "claude"

    def __init__(
        self,
        payload: str = '{"compiled":true}\n',
        mode: int | None = None,
        destination: str = ".generated/profile.json",
    ) -> None:
        self.payload = payload
        self.mode = mode
        self.destination = PurePosixPath(destination)

    def render(self, profile, target: Path, *, logical_root: Path):
        del profile
        assert logical_root.is_absolute()
        path = target.joinpath(*self.destination.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.payload, encoding="utf-8")
        if self.mode is not None:
            os.chmod(path, self.mode)
        return (self.destination,)


def _two_target_request(
    tmp_path: Path,
    *,
    second_target_root: str = "$HOME",
) -> tuple[CompileRequest, Path, Path]:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "live"
    profile_dir.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    (profile_dir / "profile.yaml").write_text(
        "name: live\ncompile_targets:\n"
        "  first:\n    target_root: $HOME\n    harnesses: [claude]\n"
        f"  second:\n    target_root: {second_target_root}\n    harnesses: [cursor]\n",
        encoding="utf-8",
    )
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    output_root = tmp_path / "compiled"
    return (
        CompileRequest(
            profile_name="live",
            source_root=source_root,
            baseline_root=baseline_root,
            output_root=output_root,
        ),
        home,
        output_root,
    )


def _request(
    tmp_path: Path,
    harnesses: str = "claude",
) -> tuple[CompileRequest, Path, Path, Path]:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "live"
    profile_dir.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    (profile_dir / "profile.yaml").write_text(
        (
            "name: live\ncompile_targets:\n  home:\n    target_root: $HOME\n"
            f"    harnesses: [{harnesses}]\n"
        ),
        encoding="utf-8",
    )
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    live_file = home / "user-owned.txt"
    live_file.write_text("keep me\n", encoding="utf-8")
    output_root = tmp_path / "compiled"
    request = CompileRequest(
        profile_name="live",
        source_root=source_root,
        baseline_root=baseline_root,
        output_root=output_root,
    )
    return request, home, live_file, output_root


def test_compile_renders_privately_and_publishes_only_under_output_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, live_file, output_root = _request(tmp_path)
    before = live_file.read_bytes()
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    manifest = compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert live_file.read_bytes() == before
    assert (output_root / "manifest.json").is_file()
    assert all(
        path.is_file() and output_root in path.parents
        for path in output_root.rglob("*")
        if path.is_file()
    )
    assert manifest.files[0].fragment_path.parts[:2] == (
        "generations",
        manifest.generation,
    )


def test_failed_compile_preserves_prior_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path)
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())
    compile_module.compile_profile(request, environment={"HOME": str(home)})
    manifest_bytes = (output_root / "manifest.json").read_bytes()
    generation = json.loads(manifest_bytes)["generation"]
    fragment = next(
        path for path in (output_root / "generations" / generation).rglob("*") if path.is_file()
    )
    fragment_bytes = fragment.read_bytes()

    monkeypatch.setattr(compile_module, "renderer", lambda harness: _FailingRenderer())
    with pytest.raises(
        ProfileCompileError,
        match="renderer 'claude'.*target 'home'.*renderer failed",
    ) as failure:
        compile_module.compile_profile(request, environment={"HOME": str(home)})
    assert isinstance(failure.value.__cause__, RuntimeError)

    assert (output_root / "manifest.json").read_bytes() == manifest_bytes
    assert fragment.read_bytes() == fragment_bytes


def test_publication_failures_are_profile_compile_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, _ = _request(tmp_path)
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    def fail_publish(*args: object, **kwargs: object) -> Path:
        del args, kwargs
        raise OSError("publication failed")

    monkeypatch.setattr(compile_module, "publish_generation", fail_publish)

    with pytest.raises(ProfileCompileError, match="publish.*publication failed") as failure:
        compile_module.compile_profile(request, environment={"HOME": str(home)})
    assert isinstance(failure.value.__cause__, OSError)


def test_identical_compile_inputs_publish_byte_identical_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path)
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    first = compile_module.compile_profile(request, environment={"HOME": str(home)})
    first_manifest = (output_root / "manifest.json").read_bytes()
    first_generation = first.generation
    first_fragment = next(
        path
        for path in (output_root / "generations" / first_generation).rglob("*")
        if path.is_file()
    )
    first_bytes = first_fragment.read_bytes()

    second = compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert second == first
    assert (output_root / "manifest.json").read_bytes() == first_manifest
    assert first_fragment.read_bytes() == first_bytes


def test_multi_harness_identical_outputs_publish_one_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path, "claude, cursor")
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    manifest = compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert len(manifest.files) == 1
    assert manifest.files[0].harness == "claude"
    generation_root = output_root / "generations" / manifest.generation
    assert (generation_root / "manifest.json").is_file()
    assert (output_root / manifest.files[0].fragment_path).is_file()
    assert len(tuple(path for path in generation_root.rglob("*") if path.is_file())) == 2


def test_multi_harness_conflicting_outputs_fail_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path, "claude, cursor")
    monkeypatch.setattr(
        compile_module,
        "renderer",
        lambda harness: _Renderer(payload=f"{harness}\n"),
    )

    with pytest.raises(ProfileCompileError, match="conflicting renderer outputs"):
        compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert not output_root.exists()


def test_compile_rejects_duplicate_absolute_destinations_across_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, output_root = _two_target_request(tmp_path)
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    with pytest.raises(ProfileCompileError, match="duplicate compiled destination"):
        compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert not output_root.exists()


def test_compile_rejects_destination_prefix_conflicts_across_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, output_root = _two_target_request(
        tmp_path,
        second_target_root="$HOME/.generated",
    )
    monkeypatch.setattr(
        compile_module,
        "renderer",
        lambda harness: _Renderer(
            destination=".generated" if harness == "claude" else "profile.json"
        ),
    )

    with pytest.raises(ProfileCompileError, match="prefix conflict"):
        compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert not output_root.exists()


def test_compile_rejects_output_inside_source_root_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _, _, _ = _request(tmp_path)
    request = request.model_copy(update={"output_root": request.source_root / "compiled"})
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _FailingRenderer())

    with pytest.raises(ProfileCompileError, match="source root"):
        compile_module.compile_profile(request, environment={"HOME": str(tmp_path / "home")})

    assert not request.output_root.exists()


def test_compile_rejects_output_inside_baseline_root_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, _, _, _ = _request(tmp_path)
    request = request.model_copy(update={"output_root": request.baseline_root / "compiled"})
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _FailingRenderer())

    with pytest.raises(ProfileCompileError, match="baseline root"):
        compile_module.compile_profile(request, environment={"HOME": str(tmp_path / "home")})

    assert not request.output_root.exists()


def test_compile_rejects_output_inside_live_target_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, _ = _request(tmp_path)
    request = request.model_copy(update={"output_root": home / "compiled"})
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _FailingRenderer())

    with pytest.raises(ProfileCompileError, match="live target"):
        compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert not request.output_root.exists()


def test_compile_rejects_output_containing_live_target_before_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "live"
    profile_dir.mkdir(parents=True)
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    live_parent = tmp_path / "live"
    target_root = live_parent / "target"
    target_root.mkdir(parents=True)
    profile_dir.joinpath("profile.yaml").write_text(
        "name: live\ncompile_targets:\n  home:\n    target_root: $HOME\n    harnesses: [claude]\n",
        encoding="utf-8",
    )
    request = CompileRequest(
        profile_name="live",
        source_root=source_root,
        baseline_root=baseline_root,
        output_root=live_parent,
    )
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _FailingRenderer())

    with pytest.raises(ProfileCompileError, match="live target"):
        compile_module.compile_profile(request, environment={"HOME": str(target_root)})

    assert not (live_parent / "manifest.json").exists()


def test_compile_rejects_baseline_symlink_before_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (request.baseline_root / "escape").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    with pytest.raises(ProfileCompileError, match="baseline"):
        compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert not output_root.exists()
    assert not (outside / ".generated").exists()


def test_executable_renderer_mode_is_bound_and_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path)
    monkeypatch.setattr(
        compile_module,
        "renderer",
        lambda harness: _Renderer(mode=0o755),
    )

    manifest = compile_module.compile_profile(request, environment={"HOME": str(home)})

    assert manifest.files[0].mode == 0o755
    published = (
        output_root
        / "generations"
        / manifest.generation
        / "home"
        / "claude"
        / ".generated"
        / "profile.json"
    )
    assert stat.S_IMODE(published.stat().st_mode) == 0o755


def test_mode_only_change_survives_compile_and_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request, home, _, output_root = _request(tmp_path)
    baseline_file = request.baseline_root / ".generated" / "profile.json"
    baseline_file.parent.mkdir(parents=True)
    baseline_file.write_bytes(b'{"compiled":true}\n')
    os.chmod(baseline_file, 0o644)
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer(mode=0o755))

    manifest = compile_module.compile_profile(request, environment={"HOME": str(home)})
    root_manifest = load_manifest(output_root / "manifest.json")

    assert stat.S_IMODE(baseline_file.stat().st_mode) == 0o644
    assert root_manifest.generation == manifest.generation
    assert root_manifest.files[0].mode == 0o755
    assert manifest.files[0].mode == 0o755

    apply_profile(
        output_root / "manifest.json",
        state_path=tmp_path / "state" / "apply-state.json",
    )

    applied = home / ".generated" / "profile.json"
    assert applied.read_bytes() == baseline_file.read_bytes()
    assert stat.S_IMODE(applied.stat().st_mode) == 0o755


def test_drift_is_leafwise_and_stably_ordered(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    live = tmp_path / "live.json"
    compiled = tmp_path / "compiled.json"
    baseline.write_text('{"b": 2, "nested": {"z": 1}}', encoding="utf-8")
    live.write_text('{"b": 3, "nested": {"z": 1}}', encoding="utf-8")
    compiled.write_text('{"b": 4, "nested": {"z": 2}}', encoding="utf-8")

    records = compute_drift(
        [
            FileComparison(
                target="home",
                destination_path=PurePosixPath(".config/profile.json"),
                baseline=baseline,
                live=live,
                compiled=compiled,
            )
        ]
    )

    assert [(record.path, record.baseline, record.live, record.compiled) for record in records] == [
        ("b", 2, 3, 4),
        ("nested.z", 1, 1, 2),
    ]


def test_drift_redacts_secret_leaves_and_whole_file_values(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.env"
    live = tmp_path / "live.env"
    compiled = tmp_path / "compiled.env"
    baseline.write_text("BASELINE_SECRET=old\n", encoding="utf-8")
    live.write_text("LIVE_SECRET=live-secret\n", encoding="utf-8")
    compiled.write_text("COMPILED_SECRET=generated\n", encoding="utf-8")

    records = compute_drift(
        [
            FileComparison(
                target="home",
                destination_path=PurePosixPath(".config/profile.env"),
                baseline=baseline,
                live=live,
                compiled=compiled,
            )
        ]
    )

    assert records[0].live["redacted"] is True
    repeated = compute_drift(
        [
            FileComparison(
                target="home",
                destination_path=PurePosixPath(".config/profile.env"),
                baseline=baseline,
                live=live,
                compiled=compiled,
            )
        ]
    )
    assert records[0].live == repeated[0].live
    assert "live-secret" not in json.dumps([record.model_dump(mode="json") for record in records])
    json_baseline = tmp_path / "baseline.json"
    json_live = tmp_path / "live.json"
    json_compiled = tmp_path / "compiled.json"
    json_baseline.write_text('{"token": "old-token"}', encoding="utf-8")
    json_live.write_text('{"token": "live-token"}', encoding="utf-8")
    json_compiled.write_text('{"token": "generated-token"}', encoding="utf-8")
    json_records = compute_drift(
        [
            FileComparison(
                target="home",
                destination_path=PurePosixPath("profile.json"),
                baseline=json_baseline,
                live=json_live,
                compiled=json_compiled,
            )
        ]
    )
    assert json_records[0].live["redacted"] is True
    assert "live-token" not in json.dumps(
        [record.model_dump(mode="json") for record in json_records]
    )


def test_drift_rejects_live_symlink_and_special_file_before_read(tmp_path: Path) -> None:
    target_root = tmp_path / "home"
    target_root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"token": "outside-secret"}', encoding="utf-8")
    live = target_root / "profile.json"
    live.symlink_to(outside)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    compiled = tmp_path / "compiled.json"
    compiled.write_text("{}", encoding="utf-8")

    comparison = FileComparison(
        target="home",
        destination_path=PurePosixPath("profile.json"),
        baseline=baseline,
        live=live,
        compiled=compiled,
    )
    with pytest.raises(DriftError, match="symlink"):
        compute_drift([comparison])

    live.unlink()
    os.mkfifo(live)
    with pytest.raises(DriftError, match="regular file"):
        compute_drift([comparison])


def test_drift_rejects_live_parent_symlink_and_out_of_root_destination(tmp_path: Path) -> None:
    target_root = tmp_path / "home"
    target_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "profile.json").write_text("{}", encoding="utf-8")
    linked_parent = target_root / "nested"
    linked_parent.symlink_to(outside, target_is_directory=True)
    baseline = tmp_path / "baseline.json"
    baseline.write_text("{}", encoding="utf-8")
    compiled = tmp_path / "compiled.json"
    compiled.write_text("{}", encoding="utf-8")

    with pytest.raises(DriftError, match="symlink"):
        compute_drift(
            [
                FileComparison(
                    target="home",
                    destination_path=PurePosixPath("nested/profile.json"),
                    baseline=baseline,
                    live=linked_parent / "profile.json",
                    compiled=compiled,
                )
            ]
        )

    with pytest.raises(DriftError, match="outside its target root"):
        compute_drift(
            [
                FileComparison(
                    target="home",
                    destination_path=PurePosixPath("../outside.json"),
                    baseline=baseline,
                    live=target_root / "outside.json",
                    compiled=compiled,
                )
            ]
        )


def test_drift_redacts_secret_maps_and_credential_urls(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    live = tmp_path / "live.json"
    compiled = tmp_path / "compiled.json"
    baseline.write_text(
        json.dumps(
            {
                "env": {"DATABASE_URL": "postgres://base:base-pass@db/base"},
                "headers": {"Authorization": "Bearer base-token"},
                "auth": {"password": "base-password"},
                "credentials": {"username": "base-user"},
                "endpoint": "postgres://endpoint:base-pass@db/base",
            }
        ),
        encoding="utf-8",
    )
    live.write_text(
        json.dumps(
            {
                "env": {"DATABASE_URL": "postgres://live:live-pass@db/live"},
                "headers": {"Authorization": "Bearer live-token"},
                "auth": {"password": "live-password"},
                "credentials": {"username": "live-user"},
                "endpoint": "postgres://endpoint:live-pass@db/live",
            }
        ),
        encoding="utf-8",
    )
    compiled.write_text(
        json.dumps(
            {
                "env": {"DATABASE_URL": "postgres://compiled:compiled-pass@db/compiled"},
                "headers": {"Authorization": "Bearer compiled-token"},
                "auth": {"password": "compiled-password"},
                "credentials": {"username": "compiled-user"},
                "endpoint": "postgres://endpoint:compiled-pass@db/compiled",
            }
        ),
        encoding="utf-8",
    )

    records = compute_drift(
        [
            FileComparison(
                target="home",
                destination_path=PurePosixPath("profile.json"),
                baseline=baseline,
                live=live,
                compiled=compiled,
            )
        ]
    )
    serialized = json.dumps(
        [record.model_dump(mode="json") for record in records],
        sort_keys=True,
    )
    for secret in (
        "base-pass",
        "live-pass",
        "compiled-pass",
        "base-token",
        "live-token",
        "compiled-token",
        "base-password",
        "live-password",
        "compiled-password",
        "postgres://",
    ):
        assert secret not in serialized
    assert {record.path for record in records} == {
        "auth.password",
        "credentials.username",
        "endpoint",
        "env.DATABASE_URL",
        "headers.Authorization",
    }
    assert all(record.live["redacted"] is True for record in records)  # type: ignore[index]


def test_source_backed_real_renderer_composition_and_hook_collision_rejection(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "real"
    registries = source_root / "registries"
    profile_dir.mkdir(parents=True)
    registries.mkdir()

    (source_root / "agents").mkdir()
    (source_root / "agents" / "static-agent.md").write_text(
        "Static agent instructions.\n", encoding="utf-8"
    )
    (source_root / "agents" / "lib").mkdir()
    (source_root / "agents" / "lib" / "shared.sh").write_text(
        "#!/bin/sh\necho shared\n", encoding="utf-8"
    )
    (source_root / "hooks").mkdir()
    (source_root / "hooks" / "static.sh").write_text("#!/bin/sh\necho static\n", encoding="utf-8")

    (registries / "agents.yaml").write_text(
        """agents:
  static-agent:
    description: Static source-backed agent
    body_path: agents/static-agent.md
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
""",
        encoding="utf-8",
    )
    hooks_registry = registries / "hooks.yaml"
    hooks_registry.write_text(
        """hooks:
  static-hook:
    event: PreToolUse
    matcher: Write
    script: hooks/static.sh
    shared_assets: [agents/lib/shared.sh]
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
""",
        encoding="utf-8",
    )
    (registries / "mcps.yaml").write_text(
        """mcps:
  static-mcp:
    command: static-mcp
    args: [--profile, real]
    env:
      TOKEN: '{{ env "TOKEN" }}'
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
""",
        encoding="utf-8",
    )

    plugin_root = source_root / "plugins" / "demo"
    payload_root = plugin_root / "payload"
    (plugin_root / ".claude-plugin").mkdir(parents=True)
    (payload_root / ".claude-plugin").mkdir(parents=True)
    (payload_root / "agents").mkdir()
    (payload_root / "skills" / "plugin-skill").mkdir(parents=True)
    (payload_root / "hooks").mkdir()
    (plugin_root / ".claude-plugin" / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "demo-market",
                "plugins": [{"name": "demo-plugin", "source": "payload"}],
            }
        ),
        encoding="utf-8",
    )
    (payload_root / ".claude-plugin" / "plugin.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Write",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "${CLAUDE_PLUGIN_ROOT}/hooks/plugin.sh",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (payload_root / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "plugin-mcp": {
                        "command": "plugin-mcp",
                        "env": {"TOKEN": "${TOKEN}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (payload_root / "agents" / "plugin-agent.md").write_text(
        "---\nname: plugin-agent\ndescription: Native plugin agent\n---\nPlugin body.\n",
        encoding="utf-8",
    )
    (payload_root / "skills" / "plugin-skill" / "SKILL.md").write_text(
        "# Plugin skill\n\nPlugin skill body.\n", encoding="utf-8"
    )
    (payload_root / "hooks" / "plugin.sh").write_text("#!/bin/sh\necho plugin\n", encoding="utf-8")
    (registries / "plugins.yaml").write_text(
        """plugins:
  demo-plugin:
    path: plugins/demo
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
    native: [claude, copilot]
""",
        encoding="utf-8",
    )
    (profile_dir / "profile.yaml").write_text(
        """name: real
description: Source-backed real renderer composition
registries:
  agents: registries/agents.yaml
  hooks: registries/hooks.yaml
  mcps: registries/mcps.yaml
  plugins: registries/plugins.yaml
env:
  TOKEN: "${TOKEN}"
isolated: true
compile_targets:
  home:
    target_root: "${HOME}"
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
""",
        encoding="utf-8",
    )

    baseline_root = tmp_path / "baseline"
    output_root = tmp_path / "output"
    live_root = tmp_path / "live"
    baseline_root.mkdir()
    live_root.mkdir()
    request = CompileRequest(
        profile_name="real",
        source_root=source_root,
        baseline_root=baseline_root,
        output_root=output_root,
    )
    manifest = compile_module.compile_profile(
        request,
        environment={"HOME": str(live_root), "TOKEN": "secret"},
    )

    assert {file.harness for file in manifest.files} == {
        "claude",
        "codex",
        "copilot",
        "crush",
        "cursor",
        "opencode",
    }
    fragments = {file: (output_root / file.fragment_path).read_bytes() for file in manifest.files}
    copilot_fragments = {
        file.destination_path: payload
        for file, payload in fragments.items()
        if file.harness == "copilot"
    }
    assert copilot_fragments
    for payload in copilot_fragments.values():
        assert source_root.as_posix().encode() not in payload
        assert b"_source_context" not in payload
    assert any(b'"TOKEN": "secret"' in payload for payload in copilot_fragments.values())
    assert any(
        file.harness == "codex"
        and file.destination_path == PurePosixPath(".codex/agents/plugin-agent.toml")
        for file in manifest.files
    )
    assert not any(
        file.harness == "copilot" and "plugin-agent" in file.destination_path.as_posix()
        for file in manifest.files
    )
    assert any(
        file.harness == "codex" and file.destination_path == PurePosixPath(".codex/hooks/plugin.sh")
        for file in manifest.files
    )
    claude_settings = next(
        payload
        for file, payload in fragments.items()
        if file.harness == "claude"
        and file.destination_path == PurePosixPath(".claude/settings.json")
    )
    assert b"demo-plugin@demo-market" in claude_settings
    for harness in ("codex", "crush", "cursor", "opencode"):
        assert any(
            file.harness == harness and b"plugin-mcp" in payload
            for file, payload in fragments.items()
        ), harness
    assert any(
        file.harness == "codex"
        and file.destination_path == PurePosixPath(".agents/skills/plugin-skill/SKILL.md")
        for file in manifest.files
    )

    (source_root / "hooks" / "other").mkdir()
    (source_root / "hooks" / "other" / "static.sh").write_text(
        "#!/bin/sh\necho conflicting\n", encoding="utf-8"
    )
    hooks_registry.write_text(
        """hooks:
  static-hook:
    event: PreToolUse
    matcher: Write
    script: hooks/static.sh
    shared_assets: [agents/lib/shared.sh]
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
  conflicting-hook:
    event: PreToolUse
    matcher: Read
    script: hooks/other/static.sh
    harnesses: [claude, codex, copilot, crush, cursor, opencode]
""",
        encoding="utf-8",
    )
    with pytest.raises(ProfileCompileError, match="conflicting generated destination"):
        compile_module.compile_profile(
            request,
            environment={"HOME": str(live_root), "TOKEN": "secret"},
        )


def test_compile_uses_only_explicit_source_root_when_ambient_channels_are_poisoned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "explicit-source"
    baseline_root = tmp_path / "baseline"
    output_root = tmp_path / "compiled"
    explicit_target = tmp_path / "explicit-target"
    baseline_root.mkdir()

    def write_profile(root: Path, description: str, target: Path) -> None:
        profile_dir = root / "profiles" / "live"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.yaml").write_text(
            (
                f"name: live\ndescription: {description}\ncompile_targets:\n"
                f"  home:\n    target_root: {target}\n    harnesses: [claude]\n"
            ),
            encoding="utf-8",
        )

    write_profile(source_root, "explicit", explicit_target)
    ambient_roots = {
        "DOTFILES_DIR": tmp_path / "dotfiles-decoy",
        "HOME": tmp_path / "home-decoy",
        "XDG_CONFIG_HOME": tmp_path / "xdg-config-decoy",
        "XDG_CACHE_HOME": tmp_path / "xdg-cache-decoy",
        "XDG_DATA_HOME": tmp_path / "xdg-data-decoy",
        "XDG_STATE_HOME": tmp_path / "xdg-state-decoy",
    }
    decoy_targets: list[Path] = []
    for variable, root in ambient_roots.items():
        decoy_target = tmp_path / f"{variable.lower()}-target"
        decoy_targets.append(decoy_target)
        write_profile(root, f"{variable.lower()} decoy", decoy_target)
        monkeypatch.setenv(variable, str(root))

    cwd = tmp_path / "cwd-decoy"
    cwd.mkdir()
    cwd_target = tmp_path / "cwd-target"
    write_profile(cwd, "cwd decoy", cwd_target)
    (cwd / ".env").write_text("DOTFILES_DIR=/wrong/source\n", encoding="utf-8")
    for directory in (".cache", ".vault"):
        write_profile(cwd / directory, f"{directory} decoy", tmp_path / f"{directory[1:]}-target")
    monkeypatch.chdir(cwd)

    class _DescriptionRenderer(_Renderer):
        def render(self, profile, target: Path, *, logical_root: Path):
            self.payload = f"{profile.description}\n"
            return super().render(profile, target, logical_root=logical_root)

    monkeypatch.setattr(compile_module, "renderer", lambda harness: _DescriptionRenderer())
    request = CompileRequest(
        profile_name="live",
        source_root=source_root,
        baseline_root=baseline_root,
        output_root=output_root,
    )

    manifest = compile_module.compile_profile(
        request,
        environment={"HOME": str(ambient_roots["HOME"])},
    )

    assert manifest.compile_targets[0].resolved_root == explicit_target.resolve()
    fragment = output_root / manifest.files[0].fragment_path
    assert fragment.read_bytes() == b"explicit\n"
    assert all(not any(target.rglob("*")) for target in (*decoy_targets, cwd_target))


def test_compile_changes_only_output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shared_parent = tmp_path / "shared"
    source_root = shared_parent / "source"
    baseline_root = shared_parent / "baseline"
    live_root = shared_parent / "live"
    output_root = shared_parent / "compiled"
    shared_parent.mkdir()
    (source_root / "profiles" / "live").mkdir(parents=True)
    (source_root / "source-only.txt").write_text("source must stay unchanged\n", encoding="utf-8")
    (source_root / "profiles" / "live" / "profile.yaml").write_text(
        (
            "name: live\ncompile_targets:\n"
            f"  home:\n    target_root: {live_root}\n    harnesses: [claude]\n"
        ),
        encoding="utf-8",
    )
    baseline_root.mkdir()
    (baseline_root / "baseline-only.txt").write_text(
        "baseline must stay unchanged\n", encoding="utf-8"
    )
    live_root.mkdir()
    (live_root / "user-owned.txt").write_text("live must stay unchanged\n", encoding="utf-8")
    (shared_parent / "sibling.txt").write_text("sibling must stay unchanged\n", encoding="utf-8")
    monkeypatch.setattr(compile_module, "renderer", lambda harness: _Renderer())

    def snapshot(root: Path, *, excluded: Path | None = None) -> tuple[tuple[object, ...], ...]:
        entries: list[tuple[object, ...]] = []
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if excluded is not None and (path == excluded or excluded in path.parents):
                continue
            relative = path.relative_to(root).as_posix()
            mode = stat.S_IMODE(path.lstat().st_mode)
            if path.is_symlink():
                entries.append((relative, "symlink", mode, os.readlink(path)))
            elif path.is_dir():
                entries.append((relative, "directory", mode, None))
            elif path.is_file():
                entries.append((relative, "file", mode, path.read_bytes()))
            else:
                entries.append((relative, "special", mode, None))
        return tuple(entries)

    before = {
        "source": snapshot(source_root),
        "baseline": snapshot(baseline_root),
        "live": snapshot(live_root),
        "shared": snapshot(shared_parent, excluded=output_root),
    }
    request = CompileRequest(
        profile_name="live",
        source_root=source_root,
        baseline_root=baseline_root,
        output_root=output_root,
    )

    manifest = compile_module.compile_profile(request, environment={})

    after = {
        "source": snapshot(source_root),
        "baseline": snapshot(baseline_root),
        "live": snapshot(live_root),
        "shared": snapshot(shared_parent, excluded=output_root),
    }
    assert after == before
    assert (output_root / "manifest.json").is_file()
    assert manifest.files
    assert all(output_root in path.parents for path in output_root.rglob("*"))


def test_compile_is_byte_deterministic_across_hash_seeds(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    profile_dir = source_root / "profiles" / "live"
    profile_dir.mkdir(parents=True)
    baseline_root = tmp_path / "baseline"
    baseline_root.mkdir()
    target_root = tmp_path / "target"
    target_root.mkdir()
    (profile_dir / "profile.yaml").write_text(
        (
            "name: live\ncompile_targets:\n"
            "  home:\n    target_root: $HOME/home\n    harnesses: [claude]\n"
            "  project:\n    target_root: $HOME/project\n    harnesses: [codex]\n"
        ),
        encoding="utf-8",
    )
    output_roots = (tmp_path / "compiled-a", tmp_path / "compiled-b")
    child = """
from pathlib import Path, PurePosixPath
import sys

import cheese_flow.profiles.compile as compile_module
from cheese_flow.profiles.models import CompileRequest


class Renderer:
    def render(self, profile, target: Path, *, logical_root: Path):
        del profile, logical_root
        files = (
            (PurePosixPath(".generated/profile.json"), b'{"compiled":true}\\n'),
            (PurePosixPath(".generated/profile.json.bak"), b'{"backup":true}\\n'),
        )
        for relative, payload in files:
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        return tuple(relative for relative, _ in files)


source_root, baseline_root, target_root, output_root = map(Path, sys.argv[1:])
compile_module.renderer = lambda harness: Renderer()
compile_module.compile_profile(
    CompileRequest(
        profile_name="live",
        source_root=source_root,
        baseline_root=baseline_root,
        output_root=output_root,
    ),
    environment={"HOME": str(target_root)},
)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "python")
    for seed, output_root in zip(("1", "2"), output_roots, strict=True):
        child_environment = environment.copy()
        child_environment["PYTHONHASHSEED"] = seed
        subprocess.run(
            [
                sys.executable,
                "-c",
                child,
                str(source_root),
                str(baseline_root),
                str(target_root),
                str(output_root),
            ],
            check=True,
            cwd=tmp_path,
            env=child_environment,
        )

    def output_bytes(root: Path) -> tuple[tuple[str, bytes], ...]:
        return tuple(
            (path.relative_to(root).as_posix(), path.read_bytes())
            for path in sorted(root.rglob("*"), key=lambda item: item.as_posix())
            if path.is_file()
        )

    assert output_bytes(output_roots[0]) == output_bytes(output_roots[1])
