"""Contract types for the cheese-flow v1 composition installer.

Every other module in the package is written against these models: the CLI and
TUI produce a :class:`DesiredState`, ``install.py`` turns it into an
:class:`InstallPlan`, and ``install.py`` / ``doctor.py`` report back with
:class:`ApplyReport` / :class:`DoctorReport`. The models own the structural
invariants (absolute paths, no duplicates, required components, resolvable step
dependencies); TOML-shape validation lives in ``desired_state.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

HarnessName = Literal["claude-code", "codex", "cursor"]
"""Harnesses supported in v1. Pi and OMP are deferred."""

HARNESS_NAMES: tuple[HarnessName, ...] = ("claude-code", "codex", "cursor")

ComponentName = Literal["hallouminate", "easy-cheese", "tilth"]
"""Cheese ecosystem components cheese-flow can install."""

COMPONENT_NAMES: tuple[ComponentName, ...] = ("hallouminate", "easy-cheese", "tilth")

REQUIRED_COMPONENTS: tuple[ComponentName, ...] = ("hallouminate", "easy-cheese")
"""Components every valid desired state must select. Tilth is optional."""

DEFAULT_MAX_DEPTH = 2
"""Default repository search depth. Depth zero means the search root itself."""


class Phase(StrEnum):
    """What a plan step does to the system."""

    INSTALL = "install"
    """Install or upgrade the component's own executable or package."""

    REGISTER = "register"
    """Register the component with a harness (plugin, MCP entry, skill install)."""

    CONFIGURE = "configure"
    """Create or validate component-owned configuration."""

    INITIALIZE = "initialize"
    """Initialize or index a selected repository."""


class StepStatus(StrEnum):
    """Outcome of a single plan step."""

    SUCCEEDED = "succeeded"
    """The postcondition holds after the step ran."""

    SKIPPED = "skipped"
    """The postcondition already held, so no mutation was performed."""

    FAILED = "failed"
    """The postcondition did not hold after the step ran."""

    BLOCKED = "blocked"
    """A dependency failed, so this step was never attempted."""

    INTERRUPTED = "interrupted"
    """SIGINT/SIGTERM arrived before the step reached a verified outcome."""


class ReportStatus(StrEnum):
    """Overall outcome of an install or doctor run."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class CollisionClass(StrEnum):
    """How a discovered repository relates to the other candidates."""

    NONE = "none"
    """No other candidate shares this repository's name or main worktree."""

    NAME = "name"
    """Another candidate at a different path has the same repository name."""

    WORKTREE = "worktree"
    """Another candidate is a linked worktree of the same main worktree."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _require_absolute(paths: Sequence[Path], label: str) -> None:
    relative = [str(p) for p in paths if not p.is_absolute()]
    if relative:
        raise ValueError(f"{label} must be absolute paths: {', '.join(relative)}")


def canonicalize(path: Path) -> Path:
    """Resolve ``path`` without requiring it to exist.

    Repository discovery canonicalizes what it finds, so anything compared
    against a discovered path has to be canonicalized the same way — otherwise
    ``~/Dev`` and its symlink target describe the same directory but never
    compare equal. Unlike discovery's own strict resolution this keeps paths
    that do not exist yet, so a user's typed search root is never discarded.
    """
    return path.resolve()


def is_under_any_root(path: Path, search_roots: Sequence[Path]) -> bool:
    """Return whether ``path`` sits under one of ``search_roots``.

    The single implementation of the selection-under-root rule: the manifest
    model enforces it and the wizard prunes against it, so a selection can never
    be offered — or persisted — once its search root goes away.
    """
    canonical = canonicalize(path)
    return any(canonical.is_relative_to(canonicalize(root)) for root in search_roots)


REDACTED = "***"
"""Marker written in place of a secret-looking argv token or config value."""

_SECRET_NAME_HINTS = ("token", "secret", "password", "passwd", "api_key", "apikey", "credential")


def _is_secret_name(name: str) -> bool:
    normalized = name.lstrip("-").lower().replace("-", "_")
    return any(hint in normalized for hint in _SECRET_NAME_HINTS)


def scan_argv(argv: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Redact secret-looking argv tokens, returning the redacted argv and the secrets found."""
    redacted: list[str] = []
    secrets: list[str] = []
    expect_value = False
    for token in argv:
        if expect_value:
            redacted.append(REDACTED)
            secrets.append(token)
            expect_value = False
            continue
        name, separator, value = token.partition("=")
        if separator and _is_secret_name(name):
            redacted.append(f"{name}={REDACTED}")
            secrets.append(value)
            continue
        redacted.append(token)
        expect_value = token.startswith("-") and _is_secret_name(token)
    return tuple(redacted), tuple(secret for secret in secrets if secret)


def redact_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Replace secret-looking argv values with a redaction marker."""
    return scan_argv(argv)[0]


def _redact_config_value(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (REDACTED if _is_secret_name(key) else _redact_nested(item))
        for key, item in value.items()
    }


def _redact_nested(item: Any) -> Any:
    if isinstance(item, dict):
        return _redact_config_value(item)
    if isinstance(item, list):
        return [_redact_nested(sub) for sub in item]
    return item


def _require_unique(
    values: Sequence[object], label: str, *, display: Sequence[object] | None = None
) -> None:
    """Detect duplicates in ``values``, naming them with ``display`` if given.

    Comparison happens on the canonical values; the message quotes what the user
    actually wrote, so two spellings of one directory are not reported as a path
    typed twice.
    """
    rendered = [str(value) for value in (values if display is None else display)]
    seen: set[object] = set()
    duplicates: list[str] = []
    for value, text in zip(values, rendered, strict=True):
        if value in seen:
            duplicates.append(text)
        seen.add(value)
    if duplicates:
        raise ValueError(f"{label} must not contain duplicates: {', '.join(duplicates)}")


class RepositorySelection(_Frozen):
    """Where to look for repositories, how deep, and which ones were chosen.

    Roots and selections are canonicalized here, at the one seam both pass
    through, so a selection can always be compared against its search root and
    a persisted manifest reloads to exactly the state that wrote it. The same
    seam rejects a selection that sits under no search root, so no producer —
    wizard or manifest — can build a state the loader would refuse.
    """

    search_roots: tuple[Path, ...] = ()
    max_depth: int = Field(default=DEFAULT_MAX_DEPTH, ge=0)
    selected: tuple[Path, ...] = ()

    @field_validator("search_roots", "selected")
    @classmethod
    def _absolute_canonical_and_unique(cls, value: tuple[Path, ...], info) -> tuple[Path, ...]:
        _require_absolute(value, info.field_name)
        canonical = tuple(canonicalize(path) for path in value)
        _require_unique(canonical, info.field_name, display=value)
        return canonical

    @model_validator(mode="after")
    def _selection_under_a_search_root(self) -> RepositorySelection:
        orphans = [
            str(selected)
            for selected in self.selected
            if not is_under_any_root(selected, self.search_roots)
        ]
        if orphans:
            raise ValueError(
                f"selected repositories are not under any search root: {', '.join(orphans)}"
            )
        return self


class DesiredState(_Frozen):
    """The full, validated user intent persisted to the TOML manifest."""

    harnesses: tuple[HarnessName, ...]
    components: tuple[ComponentName, ...]
    repositories: RepositorySelection = RepositorySelection()

    @field_validator("harnesses")
    @classmethod
    def _unique_non_empty_harnesses(cls, value: tuple[HarnessName, ...]) -> tuple[HarnessName, ...]:
        if not value:
            raise ValueError("harnesses must select at least one harness")
        _require_unique(value, "harnesses")
        return value

    @field_validator("components")
    @classmethod
    def _unique_required_components(
        cls, value: tuple[ComponentName, ...]
    ) -> tuple[ComponentName, ...]:
        _require_unique(value, "components")
        missing = [name for name in REQUIRED_COMPONENTS if name not in value]
        if missing:
            raise ValueError(f"components must include required components: {', '.join(missing)}")
        return value


class RepositoryCandidate(_Frozen):
    """A canonicalized repository found under a search root."""

    canonical_path: Path
    name: str
    main_worktree: Path
    writable: bool
    collision: CollisionClass = CollisionClass.NONE

    @field_validator("canonical_path", "main_worktree")
    @classmethod
    def _absolute(cls, value: Path, info) -> Path:
        _require_absolute((value,), info.field_name)
        return value

    @field_validator("name")
    @classmethod
    def _non_empty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value


class ConfigEdit(_Frozen):
    """A declarative JSON or TOML config mutation for a harness."""

    target: Path
    """Absolute path of the config file to edit."""

    pointer: str
    """Dotted path inside the document, such as permissions.allow."""

    value: dict[str, Any] | str
    """The object or string to set, or the string to append uniquely."""

    mode: Literal["set", "append_unique", "toml_set"] = "set"
    """Whether to set a JSON/TOML value or append one JSON string rule."""

    @field_serializer("value")
    def _serialize_value(self, value: dict[str, Any] | str) -> dict[str, Any] | str:
        return _redact_config_value(value) if isinstance(value, dict) else value

    @field_validator("target")
    @classmethod
    def _absolute_target(cls, value: Path) -> Path:
        _require_absolute((value,), "target")
        return value

    @field_validator("pointer")
    @classmethod
    def _non_empty_pointer(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("pointer must not be empty")
        return value

    @model_validator(mode="after")
    def _value_matches_mode(self) -> ConfigEdit:
        if self.mode == "set" and isinstance(self.value, dict):
            return self
        if self.mode in ("append_unique", "toml_set") and isinstance(self.value, str):
            return self
        raise ValueError(
            f"config edit mode {self.mode!r} does not accept {type(self.value).__name__}"
        )


class ConfigEditSummary(_Frozen):
    """Which config entry a step wrote, for a result that has no argv to show."""

    target: Path
    pointer: str


class PlanStep(_Frozen):
    """One deterministic unit of work an adapter contributes to the plan.

    A step either runs ``argv`` or applies ``config_edit`` — exactly one.
    """

    step_id: str
    component: ComponentName
    harness: HarnessName | None = None
    repository: Path | None = None
    phase: Phase
    argv: tuple[str, ...] = ()
    config_edit: ConfigEdit | None = None
    postcondition: str
    depends_on: tuple[str, ...] = ()

    @field_serializer("argv")
    def _serialize_argv(self, value: tuple[str, ...]) -> tuple[str, ...]:
        return redact_argv(value)

    @field_validator("step_id", "postcondition")
    @classmethod
    def _non_empty(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be empty")
        return value

    @field_validator("repository")
    @classmethod
    def _absolute_repository(cls, value: Path | None) -> Path | None:
        if value is not None:
            _require_absolute((value,), "repository")
        return value

    @field_validator("depends_on")
    @classmethod
    def _unique_dependencies(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        _require_unique(value, "depends_on")
        return value

    @model_validator(mode="after")
    def _exactly_one_action(self) -> PlanStep:
        if bool(self.argv) == (self.config_edit is not None):
            raise ValueError(f"step {self.step_id!r} must set exactly one of argv or config_edit")
        return self

    @model_validator(mode="after")
    def _no_self_dependency(self) -> PlanStep:
        if self.step_id in self.depends_on:
            raise ValueError(f"step {self.step_id!r} must not depend on itself")
        return self


class InstallPlan(_Frozen):
    """The complete, ordered set of steps derived from a desired state."""

    manifest: DesiredState
    steps: tuple[PlanStep, ...] = ()

    @model_validator(mode="after")
    def _unique_and_resolvable_step_ids(self) -> InstallPlan:
        _require_unique([step.step_id for step in self.steps], "step_id")
        seen: set[str] = set()
        for step in self.steps:
            unresolved = [dep for dep in step.depends_on if dep not in seen]
            if unresolved:
                raise ValueError(
                    f"step {step.step_id!r} depends on unknown or later steps: "
                    f"{', '.join(unresolved)}"
                )
            seen.add(step.step_id)
        return self


class StepResult(_Frozen):
    """What actually happened to one plan step, in the headless JSON shape."""

    step_id: str
    component: ComponentName
    harness: HarnessName | None = None
    repository: Path | None = None
    phase: Phase
    argv: tuple[str, ...]
    config_edit: ConfigEditSummary | None = None
    """Set instead of ``argv`` when the step's only action was a config write."""

    postcondition: str
    status: StepStatus
    exit_code: int | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None
    elapsed_ms: int = Field(ge=0)
    remediation: str | None = None


class _PlanReport(_Frozen):
    """Shared fields for the plan-execution reports (install and doctor)."""

    status: ReportStatus
    manifest: DesiredState
    plan: InstallPlan
    results: tuple[StepResult, ...] = ()

    @model_validator(mode="after")
    def _manifest_matches_plan(self) -> _PlanReport:
        if self.manifest != self.plan.manifest:
            raise ValueError("manifest must match the manifest the plan was built from")
        return self


class ApplyReport(_PlanReport):
    """Final document emitted by ``cheese install`` (including ``--dry-run``)."""


class DoctorReport(_PlanReport):
    """Final document emitted by ``cheese doctor``."""


class CommandOutcome(_Frozen):
    """Result of running one child process."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    elapsed_ms: int = Field(ge=0)


class CommandRunner(Protocol):
    """Runs child processes on behalf of planning, apply, and verification."""

    def run(self, argv: Sequence[str], *, cwd: Path | None = None) -> CommandOutcome:
        """Run ``argv`` and return its outcome without raising on nonzero exit."""
        ...


class ComponentAdapter(Protocol):
    """Native install commands and positive postconditions for one component."""

    name: ComponentName

    def plan_steps(self, state: DesiredState) -> tuple[PlanStep, ...]:
        """Return the deterministic steps this component needs for ``state``."""
        ...

    def check_postcondition(self, step: PlanStep, runner: CommandRunner) -> bool:
        """Return whether ``step``'s positive postcondition currently holds."""
        ...


ComponentAdapters = dict[ComponentName, ComponentAdapter]
