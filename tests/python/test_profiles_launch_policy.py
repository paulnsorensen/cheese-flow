"""Behavioral tests for launch-policy validation."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from cheese_flow.profiles.errors import ProfileLaunchError
from cheese_flow.profiles.launch_policy import (
    ValidatedLaunchPolicy,
    validate_launch_policy,
)
from cheese_flow.profiles.parse import ResolvedProfile
from pydantic import ValidationError


def _profile(
    *,
    isolated: bool = False,
    extra_args: Sequence[str] = (),
    permissions_allow: Sequence[str] = (),
    permissions_deny: Sequence[str] = (),
    tools: Sequence[str] = (),
    enabled_plugins: dict[str, bool] | None = None,
) -> ResolvedProfile:
    return ResolvedProfile(
        name="live",
        source_id="profiles/live",
        isolated=isolated,
        extra_args=tuple(extra_args),
        permissions_allow=tuple(permissions_allow),
        permissions_deny=tuple(permissions_deny),
        tools=tuple(tools),
        enabled_plugins=enabled_plugins or {},
    )


@pytest.mark.parametrize("harness", ["claude", "codex", "copilot", "crush", "cursor", "opencode"])
def test_policy_accepts_each_closed_launch_harness(harness: str) -> None:
    policy = validate_launch_policy(_profile(), harness, ("--version",))

    assert policy == ValidatedLaunchPolicy(
        harness=harness,
        isolated=False,
        caller_arguments=("--version",),
        profile_arguments=(),
        warnings=(),
    )


@pytest.mark.parametrize("harness", ["unknown", "", "Claude"])
def test_policy_rejects_harnesses_outside_closed_launch_set(harness: str) -> None:
    with pytest.raises(ProfileLaunchError, match="unsupported launch harness"):
        validate_launch_policy(_profile(), harness, ())


@pytest.mark.parametrize("harness", ["cursor", "copilot", "crush"])
def test_isolated_profiles_reject_harnesses_without_isolation_support(harness: str) -> None:
    with pytest.raises(ProfileLaunchError, match="do not support"):
        validate_launch_policy(_profile(isolated=True), harness, ())


@pytest.mark.parametrize(
    "argument",
    ["--allow-tool", "--allow-tool=Read", "--deny-tool", "--deny-tool=Write"],
)
def test_copilot_policy_flags_are_rejected_before_launch(argument: str) -> None:
    with pytest.raises(ProfileLaunchError, match="must be declared by the profile"):
        validate_launch_policy(_profile(), "copilot", (argument,))


@pytest.mark.parametrize(
    "harness,argument",
    [
        ("claude", "--permission-mode=bypassPermissions"),
        ("claude", "--permission_mode=bypassPermissions"),
        ("claude", "--allowedTools=Read"),
        ("claude", "--allowed-tools=Read"),
        ("claude", "--settings=caller.json"),
        ("claude", "--mcp-config=caller.json"),
        ("claude", "--dangerously-skip-permissions"),
        ("claude", "--add-dir=/tmp"),
        ("codex", "--ask-for-approval=never"),
        ("codex", "--sandbox=danger-full-access"),
        ("codex", "--config=approval_policy=never"),
        ("codex", "--approval_policy=never"),
        ("codex", "--sandbox_mode=danger-full-access"),
        ("codex", "--profile=unsafe"),
        ("codex", "--dangerously-bypass-approvals-and-sandbox"),
        ("codex", "--full-auto"),
        ("codex", "--search"),
        ("codex", "--search=true"),
        ("codex", "--remote"),
        ("codex", "--remote=server"),
        ("codex", "-a=never"),
        ("codex", "-s=danger-full-access"),
        ("codex", "-c=approval_policy=never"),
        ("codex", "-p=unsafe"),
        ("claude", "--system-prompt=caller"),
        ("claude", "--plugin-url=caller.zip"),
        ("claude", "--safe-mode"),
        ("claude", "--remote-control"),
        ("claude", "--bare"),
        ("claude", "--bare=true"),
        ("claude", "--no-bare"),
        ("codex", "--strict-config"),
        ("codex", "--ignore-rules"),
        ("codex", "--ignore-user-config"),
        ("codex", "--dangerously-bypass-hook-trust"),
        ("opencode", "--agent=build"),
        ("opencode", "--pure"),
        ("opencode", "--auto"),
        ("opencode", "--auto=true"),
        ("opencode", "-a"),
        ("opencode", "-a=true"),
    ],
)
def test_policy_options_are_rejected(harness: str, argument: str) -> None:
    with pytest.raises(ProfileLaunchError, match="cannot override profile launch policy"):
        validate_launch_policy(_profile(), harness, (argument,))


@pytest.mark.parametrize(
    "argument",
    [
        "serve",
        "web",
        "--hostname",
        "--hostname=127.0.0.1",
        "--port",
        "--port=4096",
        "--mdns",
        "--mdns=true",
        "--mdns-domain",
        "--mdns-domain=local",
        "--mdnsDomain",
        "--mdnsDomain=local",
        "--cors",
        "--cors=http://localhost",
    ],
)
def test_opencode_network_surface_is_rejected(argument: str) -> None:
    with pytest.raises(ProfileLaunchError, match="network surface"):
        validate_launch_policy(_profile(isolated=True), "opencode", (argument,))


def test_opencode_profile_network_surface_is_rejected() -> None:
    with pytest.raises(ProfileLaunchError, match="network surface"):
        validate_launch_policy(
            _profile(isolated=True, extra_args=("serve",)),
            "opencode",
            (),
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ("--replay-limit", "5", "serve"),
        ("--replayLimit", "5", "web"),
        ("--log-level", "INFO", "serve"),
        ("--logLevel", "INFO", "web"),
        ("--continue", "false", "serve"),
        ("-c", "false", "web"),
        ("--printLogs", "false", "serve"),
    ],
)
def test_opencode_network_command_after_global_option_value_is_rejected(
    arguments: tuple[str, ...],
) -> None:
    with pytest.raises(ProfileLaunchError, match="network surface"):
        validate_launch_policy(_profile(), "opencode", arguments)


@pytest.mark.parametrize(
    ("harness", "arguments"),
    [
        ("claude", ("--print", "prompt")),
        ("codex", ("--model", "gpt")),
        ("opencode", ("prompt", "serve", "web")),
        ("opencode", ("--model", "provider/model")),
        ("opencode", ("serve.md", "webpage", "ordinary prompt")),
        ("opencode", ("run", "--", "--port", "serve", "web")),
        ("opencode", ("--", "--hostname", "serve")),
    ],
)
def test_non_policy_arguments_are_preserved(harness: str, arguments: tuple[str, ...]) -> None:
    policy = validate_launch_policy(_profile(), harness, arguments)

    assert policy.caller_arguments == arguments


@pytest.mark.parametrize("arguments", ["--version", b"--version", ["--version", 1], None])
def test_caller_arguments_require_an_explicit_string_sequence(arguments: object) -> None:
    with pytest.raises(ProfileLaunchError, match="launch arguments"):
        validate_launch_policy(_profile(), "claude", arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("harness", ["claude", "opencode"])
def test_supported_isolated_harnesses_receive_profile_arguments(harness: str) -> None:
    policy = validate_launch_policy(
        _profile(isolated=True, extra_args=("--profile-mode", "strict")),
        harness,
        ("--version",),
    )

    assert policy.profile_arguments == ("--profile-mode", "strict")
    assert policy.caller_arguments == ("--version",)
    assert policy.warnings == ()


def test_isolated_opencode_rejects_tools_restriction() -> None:
    with pytest.raises(ProfileLaunchError, match="does not support tools restrictions"):
        validate_launch_policy(_profile(isolated=True, tools=("read",)), "opencode", ())


def test_isolated_opencode_rejects_enabled_plugin_restriction() -> None:
    with pytest.raises(ProfileLaunchError, match="does not support enabled_plugins restrictions"):
        validate_launch_policy(
            _profile(isolated=True, enabled_plugins={"demo": True}), "opencode", ()
        )


def test_isolated_codex_rejects_unsupported_profile_arguments() -> None:
    with pytest.raises(ProfileLaunchError, match="isolated codex does not support"):
        validate_launch_policy(
            _profile(isolated=True, extra_args=("--profile-mode", "strict")),
            "codex",
            (),
        )


def test_non_isolated_profiles_reject_unsupported_profile_arguments() -> None:
    with pytest.raises(ProfileLaunchError, match="non-isolated launches do not support"):
        validate_launch_policy(
            _profile(extra_args=("--profile-mode", "strict")),
            "claude",
            (),
        )


def test_invalid_permission_policy_fails_before_launch_projection() -> None:
    with pytest.raises(ProfileLaunchError, match="permission policy is invalid"):
        validate_launch_policy(_profile(permissions_allow=("mcp__tilth",)), "claude", ())


def test_validated_policy_is_frozen_and_contains_no_environment() -> None:
    policy = validate_launch_policy(_profile(), "claude", ("--version",))

    assert policy.model_dump() == {
        "harness": "claude",
        "isolated": False,
        "caller_arguments": ("--version",),
        "profile_arguments": (),
        "warnings": (),
    }
    with pytest.raises(ValidationError):
        policy.harness = "codex"  # type: ignore[misc]
