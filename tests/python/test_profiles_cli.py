from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from cheese_flow.profiles import cli
from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.models import LaunchSpec
from cheese_flow.profiles.source import ProfileSummary
from pydantic import BaseModel
from typer.testing import CliRunner

runner = CliRunner()


def _assert_secret_absent(result: Any, secret: str) -> None:
    for text in (
        result.output,
        result.stdout,
        result.stderr,
        str(result.exception),
        repr(result.exception),
    ):
        assert secret not in text


class _Document(BaseModel):
    value: str


def test_profile_help_exposes_only_locked_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert all(
        command in result.stdout
        for command in ("list", "describe", "compile", "apply", "launch", "permissions")
    )
    assert "\n  source " not in result.stdout
    assert "\n  render " not in result.stdout


def test_list_and_describe_use_explicit_source_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    summary = ProfileSummary(
        name="global", description="Global profile", source_id="profiles/global"
    )
    seen: dict[str, Any] = {}

    def fake_list(source_root: Path) -> tuple[ProfileSummary, ...]:
        seen["list"] = source_root
        return (summary,)

    def fake_load(source_root: Path, name: str, *, environment: dict[str, str]) -> ProfileSummary:
        seen["describe"] = (source_root, name, environment)
        return summary

    monkeypatch.setattr(cli, "list_profiles", fake_list)
    monkeypatch.setattr(cli, "load_profile", fake_load)

    source_root = tmp_path / "dotfiles"
    listed = runner.invoke(cli.app, ["list", "--source-root", str(source_root)])
    described = runner.invoke(
        cli.app,
        ["describe", "global", "--source-root", str(source_root)],
        env={"PROFILE_TEST": "present"},
    )

    assert listed.exit_code == 0
    assert json.loads(listed.stdout) == [summary.model_dump(mode="json")]
    assert described.exit_code == 0
    assert json.loads(described.stdout) == summary.model_dump(mode="json")
    assert seen["list"] == source_root
    assert seen["describe"][0:2] == (source_root, "global")
    assert seen["describe"][2]["PROFILE_TEST"] == "present"


def test_compile_and_apply_emit_engine_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}
    document = _Document(value="ok")

    def fake_compile(request: Any, *, environment: dict[str, str]) -> _Document:
        seen["compile"] = (request, environment)
        return document

    def fake_apply(manifest: Path, *, state_path: Path | None) -> _Document:
        seen["apply"] = (manifest, state_path)
        return document

    monkeypatch.setattr(cli, "compile_profile", fake_compile)
    monkeypatch.setattr(cli, "apply_profile", fake_apply)

    source_root = tmp_path / "dotfiles"
    baseline = tmp_path / "baseline"
    output = tmp_path / "publication"
    manifest = output / "manifest.json"
    state = tmp_path / "state.json"

    compiled = runner.invoke(
        cli.app,
        [
            "compile",
            "global",
            "--source-root",
            str(source_root),
            "--baseline",
            str(baseline),
            "--output",
            str(output),
        ],
    )
    applied = runner.invoke(cli.app, ["apply", str(manifest), "--state", str(state)])

    assert compiled.exit_code == 0
    assert json.loads(compiled.stdout) == {"value": "ok"}
    assert applied.exit_code == 0
    assert json.loads(applied.stdout) == {"value": "ok"}
    assert seen["compile"][0].profile_name == "global"
    assert seen["compile"][0].source_root == source_root
    assert seen["compile"][0].baseline_root == baseline
    assert seen["compile"][0].output_root == output
    assert seen["apply"] == (manifest, state)


def test_launch_exec_seam_receives_only_a_validated_launch_spec(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request_seen: dict[str, Any] = {}
    spec = LaunchSpec(
        executable="claude",
        argv=("claude", "--resume"),
        environment={"PROFILE_TEST": "present"},
    )

    def fake_build(request: Any, *, environment: dict[str, str]) -> tuple[LaunchSpec, None]:
        request_seen["request"] = request
        request_seen["environment"] = environment
        return spec, None

    executed: list[LaunchSpec] = []
    monkeypatch.setattr(cli, "_build_launch_with_workspace", fake_build)
    monkeypatch.setattr(cli, "_exec_launch", executed.append)

    result = runner.invoke(
        cli.app,
        [
            "launch",
            "claude",
            "global",
            "--source-root",
            str(tmp_path),
            "--",
            "--resume",
        ],
        env={"PROFILE_TEST": "present"},
    )

    assert result.exit_code == 0
    assert executed == [spec]
    assert isinstance(executed[0], LaunchSpec)
    assert request_seen["request"].arguments == ("--resume",)
    assert request_seen["environment"]["PROFILE_TEST"] == "present"


def test_launch_wrapper_arguments_parse_without_separator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request_seen: dict[str, Any] = {}
    spec = LaunchSpec(
        executable="codex",
        argv=("codex", "--resume"),
        environment={"PROFILE_TEST": "present"},
    )

    def fake_build(request: Any, *, environment: dict[str, str]) -> tuple[LaunchSpec, None]:
        request_seen["request"] = request
        request_seen["environment"] = environment
        return spec, None

    executed: list[LaunchSpec] = []
    monkeypatch.setattr(cli, "_build_launch_with_workspace", fake_build)
    monkeypatch.setattr(cli, "_exec_launch", executed.append)

    source_root = tmp_path / "source"
    result = runner.invoke(
        cli.app,
        [
            "launch",
            "codex",
            "demo",
            "--resume",
            "--source-root",
            str(source_root),
        ],
    )

    assert result.exit_code == 0
    assert executed == [spec]
    assert request_seen["request"].source_root == source_root
    assert request_seen["request"].harness == "codex"
    assert request_seen["request"].arguments == ("--resume",)


def test_launch_exec_rejects_unvalidated_values() -> None:
    with pytest.raises(ProfileLaunchError, match="validated LaunchSpec"):
        cli._exec_launch(object())  # type: ignore[arg-type]


def test_launch_exec_validates_environment_before_os_execvpe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def unexpected_exec(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(cli.os, "execvpe", unexpected_exec)
    spec = LaunchSpec.model_construct(
        executable="claude",
        argv=("claude",),
        environment={"": "environment-secret"},
    )

    with pytest.raises(ProfileLaunchError, match="launch environment"):
        cli._exec_launch(spec)

    assert not called


def test_launch_cleans_workspace_when_exec_raises_value_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "isolated"
    workspace.mkdir()
    spec = LaunchSpec(executable="claude", argv=("claude",), environment={})
    removed: list[Path] = []

    def fake_build(*args: object, **kwargs: object) -> tuple[LaunchSpec, Path]:
        return spec, workspace

    def fail_exec(value: LaunchSpec) -> None:
        raise ValueError("environment-secret")

    monkeypatch.setattr(cli, "_build_launch_with_workspace", fake_build)
    monkeypatch.setattr(cli, "_exec_launch", fail_exec)
    monkeypatch.setattr(cli, "remove_workspace", removed.append)

    result = runner.invoke(
        cli.app,
        ["launch", "claude", "demo", "--source-root", str(tmp_path)],
    )

    assert result.exit_code == 1
    assert removed == [workspace]
    assert "environment-secret" not in result.output


def test_launch_reports_exec_and_cleanup_failures_without_environment_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "isolated"
    workspace.mkdir()
    secret = "exec-cleanup-secret"
    spec = LaunchSpec(
        executable="claude",
        argv=("claude",),
        environment={"PROFILE_SECRET": secret},
    )

    def fake_build(*args: object, **kwargs: object) -> tuple[LaunchSpec, Path]:
        return spec, workspace

    def fail_exec(value: LaunchSpec) -> None:
        raise ValueError(secret)

    def fail_cleanup(value: Path) -> None:
        raise RuntimeError(f"cleanup failed for {secret}")

    monkeypatch.setattr(cli, "_build_launch_with_workspace", fake_build)
    monkeypatch.setattr(cli, "_exec_launch", fail_exec)
    monkeypatch.setattr(cli, "remove_workspace", fail_cleanup)

    result = runner.invoke(
        cli.app,
        ["launch", "claude", "demo", "--source-root", str(tmp_path)],
        env={"PROFILE_SECRET": secret},
    )

    assert result.exit_code == 1
    assert "could not exec harness 'claude'" in result.output
    assert "workspace cleanup failed" in result.output
    assert "cleanup failed for <redacted>" in result.output
    _assert_secret_absent(result, secret)


def test_launch_cli_redacts_build_environment_diagnostics(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = "profile-launch-secret-unique-9f3d"

    def fail_build(request: Any, *, environment: dict[str, str]) -> tuple[LaunchSpec, None]:
        raise ProfileLaunchError(f"launch build received {environment['PROFILE_LAUNCH_SECRET']}")

    monkeypatch.setattr(cli, "_build_launch_with_workspace", fail_build)
    result = runner.invoke(
        cli.app,
        [
            "launch",
            "codex",
            "demo",
            "--source-root",
            str(tmp_path),
        ],
        env={"PROFILE_LAUNCH_SECRET": secret},
    )

    assert result.exit_code == 1
    assert "launch build received <redacted>" in result.output
    _assert_secret_absent(result, secret)


def test_permissions_builds_the_closed_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: dict[str, Any] = {}

    def fake_render(request: Any, *, environment: dict[str, str]) -> _Document:
        seen["request"] = request
        seen["environment"] = environment
        return _Document(value="ok")

    monkeypatch.setattr(cli, "render_project_permissions", fake_render)
    result = runner.invoke(
        cli.app,
        [
            "permissions",
            "--project-root",
            str(tmp_path),
            "--local",
            "--harness",
            "claude",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"value": "ok"}
    assert seen["request"].project_root == tmp_path
    assert seen["request"].local is True
    assert seen["request"].harnesses == ("claude",)
