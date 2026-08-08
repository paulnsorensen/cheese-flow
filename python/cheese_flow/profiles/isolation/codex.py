"""Build an isolated Codex launch without touching the caller's home."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path

import tomlkit
from tomlkit import TOMLDocument, dumps, parse, table

from ..errors import ProfileLaunchError
from ..launch_policy import ValidatedLaunchPolicy
from ..models import LaunchSpec
from ..parse import ResolvedProfile
from ..renderers.codex import CodexRenderer
from ..rendering.permissions import launch_permission_rules
from .runtime import write_workspace_file


def build_codex_isolation(
    profile: ResolvedProfile,
    policy: ValidatedLaunchPolicy,
    workspace: Path,
    *,
    environment: Mapping[str, str],
) -> LaunchSpec:
    """Materialize an isolated Codex home and return its executable projection."""

    try:
        if not isinstance(profile, ResolvedProfile):
            raise ProfileLaunchError("isolated Codex launch requires a resolved profile")
        if policy.harness != "codex" or not policy.isolated:
            raise ProfileLaunchError("isolated Codex launch requires an isolated Codex policy")
        if policy.profile_arguments:
            raise ProfileLaunchError("isolated Codex launch cannot use profile arguments")

        root = Path(workspace)
        if not root.is_dir() or root.is_symlink():
            raise ProfileLaunchError("isolated Codex workspace is not a directory")
        if not all(
            isinstance(key, str) and isinstance(value, str) for key, value in environment.items()
        ):
            raise ProfileLaunchError("Codex launch environment must contain string keys and values")

        # Renderer templates receive the explicit launch snapshot, never the
        # process environment. Profile values take precedence for declarations,
        # while the generated Codex home remains the isolated workspace.
        launch_environment = {
            **dict(environment),
            **dict(profile.env),
            "CODEX_HOME": str(root),
        }
        launch_settings = dict(profile.settings)
        launch_settings["permissions_allow"] = launch_permission_rules(profile, "permissions_allow")
        launch_settings["permissions_deny"] = launch_permission_rules(profile, "permissions_deny")
        render_profile = profile.model_copy(
            update={"env": launch_environment, "settings": launch_settings}
        )
        CodexRenderer().render(render_profile, root, logical_root=root)
        config = _promote_codex_home(root)
        config = _apply_codex_defaults(config, profile)
        write_workspace_file(root, "config.toml", dumps(config))
        _rewrite_hook_paths(root)
        _link_authentication(root, environment)
        _lockdown_workspace(root)

        return LaunchSpec(
            executable="codex",
            argv=("codex", *policy.caller_arguments),
            environment=launch_environment,
        )
    except ProfileLaunchError:
        raise
    except Exception as exc:
        raise ProfileLaunchError("failed to build isolated Codex launch") from exc


def _promote_codex_home(root: Path) -> TOMLDocument:
    codex_root = root / ".codex"
    config_path = codex_root / "config.toml"
    if config_path.is_file():
        config = parse(config_path.read_text(encoding="utf-8"))
    else:
        config = tomlkit.document()

    if codex_root.exists():
        if codex_root.is_symlink() or not codex_root.is_dir():
            raise ProfileLaunchError("Codex renderer produced an invalid home")
        for child in tuple(codex_root.iterdir()):
            if child.name == "config.toml":
                child.unlink()
                continue
            destination = root / child.name
            if destination.exists() or destination.is_symlink():
                raise ProfileLaunchError("Codex workspace contains a conflicting generated path")
            shutil.move(str(child), str(destination))
        codex_root.rmdir()
    return config


def _apply_codex_defaults(config: TOMLDocument, profile: ResolvedProfile) -> TOMLDocument:
    config["approval_policy"] = "on-request"
    config["approvals_reviewer"] = "auto_review"
    config["sandbox_mode"] = "workspace-write"

    tui = config.get("tui")
    if not isinstance(tui, Mapping):
        tui = table()
        config["tui"] = tui
    tui["input_mode"] = "vim"

    if profile.system_prompt:
        prompt = Path(profile.system_prompt)
        if not prompt.is_absolute() or not prompt.is_file() or prompt.is_symlink():
            raise ProfileLaunchError("Codex system prompt must be an existing regular file")
        config["model_instructions_file"] = str(prompt)
    return config


def _rewrite_hook_paths(root: Path) -> None:
    hooks = root / "hooks.json"
    if not hooks.is_file() or hooks.is_symlink():
        return
    old_root = str(root / ".codex")
    text = hooks.read_text(encoding="utf-8")
    if old_root in text:
        hooks.write_text(text.replace(old_root, str(root)), encoding="utf-8")


def _link_authentication(root: Path, environment: Mapping[str, str]) -> None:
    home_value = environment.get("HOME")
    if not home_value:
        return
    home = Path(home_value)
    if not home.is_absolute():
        return
    auth = home / ".codex" / "auth.json"
    if not auth.is_file() or auth.is_symlink():
        return
    destination = root / "auth.json"
    if destination.exists() or destination.is_symlink():
        raise ProfileLaunchError("Codex workspace contains a conflicting authentication path")
    destination.symlink_to(auth)


def _lockdown_workspace(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir():
            path.chmod(0o700)
        else:
            path.chmod(0o600)


__all__ = ["build_codex_isolation"]
