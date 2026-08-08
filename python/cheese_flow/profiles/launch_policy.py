"""Validate profile launch policy before any harness projection or exec."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.models import LaunchHarnessName
from cheese_flow.profiles.parse import ResolvedProfile
from cheese_flow.profiles.renderers.registry import (
    ISOLATED_LAUNCH_HARNESSES,
    LAUNCH_HARNESSES,
)
from cheese_flow.profiles.rendering.permissions import validate_permission_rules

_POLICY_FLAGS = frozenset({"--allow-tool", "--deny-tool"})
_PROFILE_ARGUMENT_HARNESSES = frozenset({"claude", "opencode"})
_CLAUDE_PROTECTED_FLAGS = frozenset(
    {
        "--add-dir",
        "--agent",
        "--agents",
        "--allow-dangerously-skip-permissions",
        "--allowed-tools",
        "--allowedtools",
        "--append-system-prompt",
        "--append-system-prompt-file",
        "--bare",
        "--no-bare",
        "--dangerously-skip-permissions",
        "--disallowed-tools",
        "--disallowedtools",
        "--mcp-config",
        "--permission-mode",
        "--permission-prompt-tool",
        "--plugin-dir",
        "--plugin-url",
        "--remote-control",
        "--remote-control-session-name-prefix",
        "--safe-mode",
        "--settings",
        "--setting-sources",
        "--strict-mcp-config",
        "--system-prompt",
        "--tmux",
        "--tools",
        "--worktree",
    }
)
_CODEX_PROTECTED_FLAGS = frozenset(
    {
        "--add-dir",
        "--approval-policy",
        "--ask-for-approval",
        "--cd",
        "--config",
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "--disable",
        "--enable",
        "--full-auto",
        "--ignore-rules",
        "--ignore-user-config",
        "--instructions",
        "--no-project-doc",
        "--profile",
        "--remote",
        "--root",
        "--sandbox",
        "--sandbox-mode",
        "--search",
        "--skip-git-repo-check",
        "--strict-config",
        "--yolo",
    }
)
_CODEX_PROTECTED_SHORT_FLAGS = frozenset({"-a", "-c", "-p", "-s"})
_CLAUDE_PROTECTED_SHORT_FLAGS = frozenset({"-w"})
_OPENCODE_PROTECTED_FLAGS = frozenset({"--agent", "--auto", "--pure"})
_OPENCODE_PROTECTED_SHORT_FLAGS = frozenset({"-a"})
_OPENCODE_NETWORK_COMMANDS = frozenset({"serve", "web"})
_OPENCODE_NETWORK_FLAGS = frozenset(
    {
        "--cors",
        "--hostname",
        "--mdns",
        "--mdns-domain",
        "--mdnsdomain",
        "--port",
    }
)
_CODEX_EXTRA_ARGS_ERROR = "isolated codex does not support profile extra_args"
_OPENCODE_VALUE_FLAGS = frozenset(
    {
        "--agent",
        "--log-level",
        "--loglevel",
        "--model",
        "--prompt",
        "--replay-limit",
        "--replaylimit",
        "--session",
        "-m",
        "-s",
    }
)
_OPENCODE_BOOLEAN_FLAGS = frozenset(
    {
        "--auto",
        "--continue",
        "--fork",
        "--help",
        "--mini",
        "--no-replay",
        "--noreplay",
        "--print-logs",
        "--printlogs",
        "--pure",
        "--version",
        "-a",
        "-c",
        "-h",
        "-v",
    }
)
_NON_ISOLATED_EXTRA_ARGS_ERROR = "non-isolated launches do not support profile extra_args"


class ValidatedLaunchPolicy(BaseModel):
    """Immutable launch decisions derived from one resolved profile."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    harness: LaunchHarnessName
    isolated: bool
    caller_arguments: tuple[str, ...]
    profile_arguments: tuple[str, ...]
    warnings: tuple[str, ...]


def _string_sequence(value: object, *, label: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ProfileLaunchError(f"{label} must be a sequence of strings")
    try:
        values = tuple(value)
    except Exception:
        raise ProfileLaunchError(f"{label} must be a sequence of strings") from None
    if any(not isinstance(item, str) for item in values):
        raise ProfileLaunchError(f"{label} must contain only strings")
    if any("\x00" in item for item in values):
        raise ProfileLaunchError(f"{label} must not contain NUL bytes")
    return values


def _caller_arguments(arguments: object) -> tuple[str, ...]:
    return _string_sequence(arguments, label="launch arguments")


def _normalized_option(argument: str) -> str:
    return argument.split("=", 1)[0].replace("_", "-").lower()


def _is_opencode_network_argument(argument: str) -> bool:
    return _normalized_option(argument) in _OPENCODE_NETWORK_FLAGS


def _reject_opencode_network_arguments(arguments: Sequence[str]) -> None:
    positional_seen = False
    value_pending = False
    for index, argument in enumerate(arguments):
        if argument == "--":
            break
        if _is_opencode_network_argument(argument):
            raise ProfileLaunchError(
                "isolated OpenCode launch cannot expose a service or network surface"
            )
        if value_pending:
            value_pending = False
            continue
        normalized = _normalized_option(argument)
        if argument.startswith("-"):
            if "=" not in argument:
                value_pending = normalized in _OPENCODE_VALUE_FLAGS or (
                    normalized in _OPENCODE_BOOLEAN_FLAGS
                    and index + 1 < len(arguments)
                    and arguments[index + 1].lower() in {"false", "true"}
                )
            continue
        if not positional_seen:
            if argument in _OPENCODE_NETWORK_COMMANDS:
                raise ProfileLaunchError(
                    "isolated OpenCode launch cannot expose a service or network surface"
                )
            positional_seen = True


def _is_protected_option(harness: str, option: str) -> bool:
    normalized = _normalized_option(option)
    if harness == "claude":
        return normalized in _CLAUDE_PROTECTED_FLAGS or normalized.startswith(
            tuple(_CLAUDE_PROTECTED_SHORT_FLAGS)
        )
    if harness == "codex":
        return normalized in _CODEX_PROTECTED_FLAGS or normalized.startswith(
            tuple(_CODEX_PROTECTED_SHORT_FLAGS)
        )
    if harness == "opencode":
        return normalized in _OPENCODE_PROTECTED_FLAGS or normalized.startswith(
            tuple(_OPENCODE_PROTECTED_SHORT_FLAGS)
        )
    return False


def _reject_caller_policy_flags(harness: str, arguments: Sequence[str]) -> None:
    for argument in arguments:
        if harness == "copilot" and _normalized_option(argument) in _POLICY_FLAGS:
            raise ProfileLaunchError(
                "Copilot launch policy flags must be declared by the profile, not the caller"
            )
        if harness in {"claude", "codex", "opencode"} and _is_protected_option(harness, argument):
            raise ProfileLaunchError(
                f"{harness} caller options cannot override profile launch policy"
            )


def _reject_unsupported_opencode_declarations(
    profile: ResolvedProfile, harness: str, isolated: bool
) -> None:
    if not isolated or harness != "opencode":
        return
    if profile.enabled_plugins:
        raise ProfileLaunchError("isolated OpenCode does not support enabled_plugins restrictions")
    if profile.tools:
        raise ProfileLaunchError("isolated OpenCode does not support tools restrictions")


def _validate_permissions(profile: ResolvedProfile) -> None:
    try:
        validate_permission_rules(profile.permissions_allow)
        validate_permission_rules(profile.permissions_deny)
    except (TypeError, ValueError):
        raise ProfileLaunchError("profile permission policy is invalid") from None


def validate_launch_policy(
    profile: ResolvedProfile,
    harness: str,
    arguments: Sequence[str],
) -> ValidatedLaunchPolicy:
    """Validate launch support and return the immutable policy projection."""
    if not isinstance(profile, ResolvedProfile):
        raise ProfileLaunchError("launch requires a resolved profile")
    if not isinstance(harness, str) or harness not in LAUNCH_HARNESSES:
        raise ProfileLaunchError("unsupported launch harness")
    caller_arguments = _caller_arguments(arguments)
    _reject_caller_policy_flags(harness, caller_arguments)
    if type(profile.isolated) is not bool:
        raise ProfileLaunchError("profile isolated must be a boolean")
    isolated = profile.isolated
    if isolated and harness not in ISOLATED_LAUNCH_HARNESSES:
        raise ProfileLaunchError(f"isolated profiles do not support harness {harness!r}")
    _reject_unsupported_opencode_declarations(profile, harness, isolated)

    _validate_permissions(profile)
    profile_values = _string_sequence(profile.extra_args, label="profile extra_args")

    if harness == "opencode":
        _reject_opencode_network_arguments((*profile_values, *caller_arguments))
    if profile_values and not isolated:
        raise ProfileLaunchError(_NON_ISOLATED_EXTRA_ARGS_ERROR)
    if profile_values and isolated and harness == "codex":
        raise ProfileLaunchError(_CODEX_EXTRA_ARGS_ERROR)

    profile_arguments: tuple[str, ...] = ()
    if isolated and harness in _PROFILE_ARGUMENT_HARNESSES:
        profile_arguments = profile_values

    return ValidatedLaunchPolicy(
        harness=harness,
        isolated=isolated,
        caller_arguments=caller_arguments,
        profile_arguments=profile_arguments,
        warnings=(),
    )


__all__ = ["ValidatedLaunchPolicy", "validate_launch_policy"]
