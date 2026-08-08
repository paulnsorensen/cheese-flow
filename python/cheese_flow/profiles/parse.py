"""Parse profile definitions from one explicit source root."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_serializer,
    field_validator,
)

from .errors import ProfileSourceError
from .models import CompileTarget
from .paths import (
    resolve_declared_path,
    resolve_profile_dir,
    resolve_profile_file,
    resolve_within,
    source_id,
    validate_explicit_source_root,
    validate_name,
    validate_relative_path,
)

_ITEM_SECTIONS = ("mcps", "agents", "skills", "commands", "hooks")
_PATH_FIELDS = ("body_path", "path", "script")
_ENV_REF_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")
_COMPILE_HARNESSES = {"claude", "codex", "copilot", "crush", "cursor", "opencode"}
_DRIVABLE_HARNESSES = {"claude", "codex", "copilot"}
_NATIVE_PLUGIN_HARNESSES = {"claude", "copilot"}
_STRING_ITEM_FIELDS = (
    "args",
    "disabled_tools",
    "disallowedTools",
    "skills",
    "tools",
)
_STRING_ITEM_SCALARS = (
    "body_path",
    "command",
    "description",
    "event",
    "matcher",
    "marketplace_name",
    "path",
    "script",
    "type",
    "url",
)

_PROFILE_KEYS = frozenset(
    {
        "name",
        "description",
        "include",
        "mcps",
        "agents",
        "skills",
        "commands",
        "hooks",
        "registries",
        "settings",
        "isolated",
        "system_prompt",
        "tools",
        "permissions_deny",
        "permissions_allow",
        "enabled_plugins",
        "env",
        "extra_args",
        "target_default",
        "marketplaces",
        "mcp_scope",
        "compile_targets",
    }
)
_COMPILE_TARGET_KEYS = frozenset({"target_root", "harnesses"})
_PLUGIN_KEYS = frozenset(
    {
        "name",
        "path",
        "git",
        "branch",
        "harnesses",
        "native",
        "claude_native",
        "codex_native",
        "copilot_native",
        "gate_unless",
        "description",
        "marketplace_name",
    }
)
_REGISTRY_KEYS = frozenset({"mcps", "agents", "skills", "hooks", "plugins"})
_NATIVE_MARKERS = {
    "claude": "_from_native_plugin",
    "codex": "_from_codex_native_plugin",
    "copilot": "_from_copilot_native_plugin",
}
_PLUGIN_AGENT_HARNESSES = ("claude", "codex", "opencode", "cursor", "copilot")
_PLUGIN_MCP_HARNESSES = ("claude", "codex", "opencode", "cursor", "copilot", "crush")
_PLUGIN_SKILL_HARNESSES = ("claude", "codex", "opencode", "cursor", "copilot")
_PLUGIN_HOOK_HARNESSES = ("claude", "codex", "copilot", "cursor")
_PLUGIN_COMMAND_HOOK_HARNESSES = ("claude", "codex")


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        from types import MappingProxyType

        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    return value


class ProfileSummary(BaseModel):
    """The inspectable identity and description of one profile source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str = ""
    source_id: str

    @field_validator("source_id")
    @classmethod
    def _source_id_is_relative(cls, value: str) -> str:
        return validate_relative_path(value, kind="source_id")


class ResolvedProfile(BaseModel):
    """A validated profile with includes and declared registries expanded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str = ""
    source_id: str
    mcps: tuple[Mapping[str, Any], ...] = ()
    agents: tuple[Mapping[str, Any], ...] = ()
    skills: tuple[Mapping[str, Any], ...] = ()
    commands: tuple[Mapping[str, Any], ...] = ()
    hooks: tuple[Mapping[str, Any], ...] = ()
    settings: Mapping[str, Any] = Field(default_factory=dict)
    isolated: bool = False
    system_prompt: str | None = None
    tools: tuple[str, ...] = ()
    permissions_deny: tuple[str, ...] = ()
    permissions_allow: tuple[str, ...] = ()
    enabled_plugins: Mapping[str, bool] = Field(default_factory=dict)
    env: Mapping[str, str] = Field(default_factory=dict)
    extra_args: tuple[str, ...] = ()
    target_default: str | None = None
    marketplaces: Mapping[str, str] = Field(default_factory=dict)
    mcp_scope: Literal["plugin", "user"] = "plugin"
    native_plugins: tuple[Mapping[str, Any], ...] = ()
    compile_targets: tuple[CompileTarget, ...] = ()

    _template_environment: Mapping[str, str] = PrivateAttr(
        default_factory=lambda: MappingProxyType({})
    )

    @property
    def template_environment(self) -> Mapping[str, str]:
        """Caller/source values available only to renderer templates."""
        return self._template_environment

    @field_serializer(
        "mcps",
        "agents",
        "skills",
        "commands",
        "hooks",
        "settings",
        "enabled_plugins",
        "env",
        "marketplaces",
        "native_plugins",
    )
    def _serialize_frozen_values(self, value: Any) -> Any:
        return _json_value(value)

    @field_validator("source_id")
    @classmethod
    def _source_id_is_relative(cls, value: str) -> str:
        return validate_relative_path(value, kind="source_id")

    @field_validator("mcps", "agents", "skills", "commands", "hooks", "native_plugins")
    @classmethod
    def _snapshot_items(cls, value: tuple[Mapping[str, Any], ...]) -> tuple[Mapping[str, Any], ...]:
        return tuple(_freeze(item) for item in value)

    @field_validator("settings", "enabled_plugins", "env", "marketplaces")
    @classmethod
    def _snapshot_mappings(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        return _freeze(value)


_EMPTY_SECTIONS: dict[str, list[dict[str, Any]]] = {section: [] for section in _ITEM_SECTIONS}
_EMPTY_SECTIONS["native_plugins"] = []


def _as_mapping(value: Any, *, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileSourceError(f"{where} must be a YAML mapping")
    return value


def _string_sequence(value: Any, *, where: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ProfileSourceError(f"{where} must be a sequence of strings")
    values = tuple(value)
    for index, entry in enumerate(values):
        if not isinstance(entry, str):
            raise ProfileSourceError(f"{where}[{index}] must be a string")
    return values


def _string_mapping(value: Any, *, where: str) -> dict[str, str]:
    mapping = _as_mapping(value, where=where)
    out: dict[str, str] = {}
    for key, entry in mapping.items():
        if not isinstance(key, str):
            raise ProfileSourceError(f"{where} keys must be strings")
        if not isinstance(entry, str):
            raise ProfileSourceError(f"{where}[{key!r}] must be a string")
        out[key] = entry
    return out


def _mapping_with_string_keys(value: Any, *, where: str) -> dict[str, Any]:
    mapping = _as_mapping(value, where=where)
    out: dict[str, Any] = {}
    for key, entry in mapping.items():
        if not isinstance(key, str):
            raise ProfileSourceError(f"{where} keys must be strings")
        out[key] = entry
    return out


def _boolean_mapping(value: Any, *, where: str) -> dict[str, bool]:
    mapping = _as_mapping(value, where=where)
    out: dict[str, bool] = {}
    for key, entry in mapping.items():
        if not isinstance(key, str):
            raise ProfileSourceError(f"{where} keys must be strings")
        out[key] = _boolean(entry, where=f"{where}[{key!r}]")
    return out


def _settings_mapping(value: Any, *, where: str) -> dict[str, Any]:
    settings = _mapping_with_string_keys(value, where=where)
    for field in ("permissions_allow", "permissions_deny"):
        if field in settings:
            settings[field] = list(_string_sequence(settings[field], where=f"{where}.{field}"))
    return settings


def _boolean(value: Any, *, where: str) -> bool:
    if not isinstance(value, bool):
        raise ProfileSourceError(f"{where} must be a boolean")
    return value


def _field_string_sequence(raw: Mapping[str, Any], field: str, *, where: str) -> list[str]:
    if field not in raw:
        return []
    return list(_string_sequence(raw[field], where=f"{where}.{field}"))


def _reject_unknown_keys(raw: Mapping[str, Any], *, allowed: frozenset[str], where: str) -> None:
    unknown = sorted(key for key in raw if not isinstance(key, str) or key not in allowed)
    if unknown:
        raise ProfileSourceError(f"{where} contains unsupported keys: {unknown}")


def _template_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Return the explicit caller snapshot available to renderer templates."""
    return dict(environment)


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate YAML mapping keys."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _as_items(value: Any, *, where: str) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ProfileSourceError(f"{where} must be a YAML list")
    items: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ProfileSourceError(f"{where}[{index}] must be a YAML mapping")
        items.append(item)
    return items


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ProfileSourceError(f"could not read YAML source {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ProfileSourceError(f"YAML source {path} must be a mapping")
    return dict(raw)


def _validate_profile_identity(
    profile_dir: Path,
    raw_name: Any,
    *,
    manifest_path: Path,
) -> str:
    if raw_name in (None, ""):
        raise ProfileSourceError(f"{manifest_path} is missing required field 'name'")
    name = validate_name(raw_name, kind="profile name")
    directory_name = validate_name(profile_dir.name, kind="profile directory name")
    if name != directory_name:
        raise ProfileSourceError(
            f"{manifest_path} name {name!r} must match profile directory {directory_name!r}"
        )
    return directory_name


def _validate_item_paths(
    item: Mapping[str, Any], *, source_root: Path, source_dir: Path, where: str
) -> None:
    for field_name in _PATH_FIELDS:
        value = item.get(field_name)
        if value in (None, ""):
            continue
        relative = validate_relative_path(value, kind=f"{where}.{field_name}")
        candidate = source_dir.joinpath(*PurePosixPath(relative).parts)
        resolve_within(source_root, candidate, kind=f"{where}.{field_name}")
    assets = item.get("shared_assets")
    if assets is None:
        return
    for index, asset in enumerate(_string_sequence(assets, where=f"{where}.shared_assets")):
        relative = validate_relative_path(asset, kind=f"{where}.shared_assets[{index}]")
        candidate = source_dir.joinpath(*PurePosixPath(relative).parts)
        resolve_within(source_root, candidate, kind=f"{where}.shared_assets[{index}]")


def _validate_item_fields(item: dict[str, Any], *, where: str) -> None:
    if "name" in item:
        validate_name(item["name"], kind=f"{where}.name")
    for field in _STRING_ITEM_FIELDS:
        if field in item:
            item[field] = list(_string_sequence(item[field], where=f"{where}.{field}"))
    for field in _STRING_ITEM_SCALARS:
        if field in item and not isinstance(item[field], str):
            raise ProfileSourceError(f"{where}.{field} must be a string")
    if "harnesses" in item:
        harnesses = _string_sequence(item["harnesses"], where=f"{where}.harnesses")
        for harness in harnesses:
            if harness not in _COMPILE_HARNESSES:
                raise ProfileSourceError(f"{where}.harnesses has unknown harness {harness!r}")
        item["harnesses"] = list(harnesses)
    for field in ("models", "env", "headers"):
        if field in item:
            item[field] = _string_mapping(item[field], where=f"{where}.{field}")
    for field in ("async", "disabled", "optional"):
        if field in item:
            item[field] = _boolean(item[field], where=f"{where}.{field}")


def _item_context(item: Mapping[str, Any], *, section: str, index: int) -> str:
    return str(item.get("_source_context") or item.get("_source_dir") or f"{section}[{index}]")


def _validate_unique_items(sections: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    for section in (*_ITEM_SECTIONS, "native_plugins"):
        seen: dict[str, str] = {}
        for index, item in enumerate(sections.get(section, ())):
            name = item.get("name")
            if not isinstance(name, str):
                continue
            context = _item_context(item, section=section, index=index)
            previous = seen.get(name)
            if previous is not None:
                raise ProfileSourceError(
                    f"duplicate {section} item name {name!r}: {previous} conflicts with {context}"
                )
            seen[name] = context


def _decorate_items(
    values: Any, *, source_root: Path, source_dir: Path, where: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(_as_items(values, where=where)):
        item = dict(raw)
        _validate_item_fields(item, where=f"{where}[{index}]")
        item.pop("fallback", None)
        _validate_item_paths(
            item, source_root=source_root, source_dir=source_dir, where=f"{where}[{index}]"
        )
        item["_source_dir"] = str(source_dir)
        item["_source_context"] = f"{where}[{index}]"
        out.append(item)
    return out


def _registry_items(path: Path, *, section: str, source_root: Path) -> list[dict[str, Any]]:
    data = _load_yaml_mapping(path)
    values = data.get(section)
    if values is None:
        return []
    if not isinstance(values, Mapping):
        raise ProfileSourceError(f"registry {path} field {section!r} must be a mapping")
    out: list[dict[str, Any]] = []
    for name, raw in values.items():
        validate_name(name, kind=f"{section} registry name")
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ProfileSourceError(f"registry {path} entry {name!r} must be a mapping")
        item = dict(raw)
        if "name" in item and item["name"] != name:
            raise ProfileSourceError(
                f"registry {path} entry {name!r} has conflicting item name {item['name']!r}"
            )
        item["name"] = name
        _validate_item_fields(item, where=f"registry {path} {name!r}")
        item["_source_dir"] = str(source_root)
        item["_source_context"] = f"{path}:{section}[{name!r}]"
        _validate_item_paths(
            item, source_root=source_root, source_dir=source_root, where=f"registry {path} {name!r}"
        )
        out.append(item)
    return out


def _external_skill_items(path: Path, *, source_root: Path) -> list[dict[str, Any]]:
    data = _load_yaml_mapping(path)
    sources = data.get("sources", {})
    if not isinstance(sources, Mapping):
        raise ProfileSourceError(f"skills registry {path} field 'sources' must be a mapping")
    out: list[dict[str, Any]] = []

    for repository, raw in sources.items():
        if not isinstance(repository, str):
            raise ProfileSourceError(f"skills registry {path} source names must be strings")
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ProfileSourceError(
                f"skills registry {path} entry {repository!r} must be a mapping"
            )
        names = raw.get("skills", [])
        names = _string_sequence(names, where=f"skills registry {path} entry {repository!r}.skills")
        for name in names:
            validate_name(name, kind="skills registry name")
            item = {
                "name": name,
                "source": repository,
                "_source_dir": str(source_root),
                "_source_context": f"{path}:sources[{repository!r}].skills[{name!r}]",
            }
            if raw.get("pin") is not None:
                if not isinstance(raw["pin"], str):
                    raise ProfileSourceError(
                        f"skills registry {path} entry {repository!r}.pin must be a string"
                    )
                item["pin"] = raw["pin"]
            out.append(item)
        if not names:
            item = {
                "source": repository,
                "_source_dir": str(source_root),
                "_source_context": f"{path}:sources[{repository!r}]",
            }
            if raw.get("pin") is not None:
                if not isinstance(raw["pin"], str):
                    raise ProfileSourceError(
                        f"skills registry {path} entry {repository!r}.pin must be a string"
                    )
                item["pin"] = raw["pin"]
            out.append(item)
    return out


def _local_skill_items(path: Path, *, source_root: Path) -> list[dict[str, Any]]:
    tree = resolve_within(source_root, path, kind="skills registry directory")
    if not tree.is_dir():
        raise ProfileSourceError(f"skills registry directory was not found: {path}")
    tree_relative = PurePosixPath(*tree.relative_to(source_root).parts)
    out: list[dict[str, Any]] = []
    for child in sorted(tree.iterdir(), key=lambda item: item.name):
        child = resolve_within(source_root, child, kind=f"skill {child.name!r}")
        if not child.is_dir():
            continue
        skill_file = resolve_within(
            source_root, child / "SKILL.md", kind=f"skill {child.name!r} body"
        )
        if skill_file.is_file():
            out.append(
                {
                    "name": child.name,
                    "path": (tree_relative / child.name).as_posix(),
                    "_source_dir": str(source_root),
                }
            )
    return out


def _plugin_native_harnesses(body: Mapping[str, Any], *, name: str, where: str) -> set[str]:
    requested = set(
        _string_sequence(body.get("harnesses", ()), where=f"{where}.harnesses")
        if "harnesses" in body
        else ()
    )
    unknown = sorted(requested - _COMPILE_HARNESSES)
    if unknown:
        raise ProfileSourceError(f"{where}.harnesses has unknown harnesses {unknown}")

    native_value = body.get("native", False)
    if isinstance(native_value, bool):
        native = (
            ((_NATIVE_PLUGIN_HARNESSES & requested) if requested else set(_NATIVE_PLUGIN_HARNESSES))
            if native_value
            else set()
        )
    else:
        native = set(_string_sequence(native_value, where=f"{where}.native"))
    for harness in _DRIVABLE_HARNESSES:
        alias = f"{harness}_native"
        if alias in body:
            native_enabled = _boolean(body[alias], where=f"{where}.{alias}")
            if native_enabled:
                native.add(harness)
    unsupported = sorted(native - _DRIVABLE_HARNESSES)
    if unsupported:
        raise ProfileSourceError(f"{where}.native has unsupported harnesses {unsupported}")
    if requested:
        outside = sorted(native - requested)
        if outside:
            raise ProfileSourceError(
                f"{where}.native has harnesses {outside} outside declared harnesses"
            )
    if "codex" in native:
        raise ProfileSourceError(
            f"{where} declares codex-native output, which the Codex renderer "
            "does not project; use explicit codex items"
        )
    return native


def _plugin_effective_harnesses(
    requested: Sequence[str],
    supported: Sequence[str],
    native: set[str],
) -> list[str]:
    values = list(requested) if requested else list(supported)
    return [value for value in values if value in supported and value not in native]


def _stamp_plugin_native(item: dict[str, Any], native: set[str]) -> None:
    for harness, marker in _NATIVE_MARKERS.items():
        if harness in native:
            item[marker] = True


def _resolve_plugin_relative(
    root: Path, value: object, *, source_root: Path, kind: str, plugin: str
) -> Path:
    if not isinstance(value, str):
        raise ProfileSourceError(f"plugin {plugin!r} {kind} must be a relative path")
    if value in ("", ".", "./"):
        return resolve_within(source_root, root, kind=f"plugin {plugin!r} {kind}")
    relative = validate_relative_path(value, kind=f"plugin {plugin!r} {kind}")
    candidate = root.joinpath(*PurePosixPath(relative).parts)
    return resolve_within(source_root, candidate, kind=f"plugin {plugin!r} {kind}")


def _plugin_frontmatter(path: Path, *, plugin: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return {}
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line == "---")
    except StopIteration as exc:
        raise ProfileSourceError(
            f"plugin {plugin!r} agent {path} has unterminated frontmatter"
        ) from exc
    try:
        raw = yaml.load("\n".join(lines[1:end]), Loader=_UniqueKeyLoader) or {}
    except yaml.YAMLError as exc:
        raise ProfileSourceError(
            f"plugin {plugin!r} agent {path} frontmatter is invalid: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise ProfileSourceError(f"plugin {plugin!r} agent {path} frontmatter must be a mapping")
    return dict(raw)


def _plugin_agents(
    plugin: str,
    payload_root: Path,
    source_root: Path,
    requested: Sequence[str],
    native: set[str],
    context: str,
) -> list[dict[str, Any]]:
    agents_root = resolve_within(
        source_root, payload_root / "agents", kind=f"plugin {plugin!r} agents"
    )
    if not agents_root.is_dir():
        return []
    harnesses = _plugin_effective_harnesses(requested, _PLUGIN_AGENT_HARNESSES, native)
    out: list[dict[str, Any]] = []
    for raw_path in sorted(agents_root.glob("*.md"), key=lambda item: item.name):
        path = resolve_within(source_root, raw_path, kind=f"plugin {plugin!r} agent")
        if not path.is_file():
            continue
        frontmatter = _plugin_frontmatter(path, plugin=plugin)
        name = frontmatter.get("name") or path.stem
        item: dict[str, Any] = {
            "name": name,
            "body_path": f"agents/{path.name}",
            "harnesses": harnesses,
            "_source_dir": str(payload_root),
            "_source_context": f"{context}:agents[{path.name!r}]",
        }
        for field in ("description", "color", "effort"):
            if frontmatter.get(field) is not None:
                item[field] = frontmatter[field]
        for field in ("tools", "disallowedTools", "skills"):
            if frontmatter.get(field) is not None:
                value = frontmatter[field]
                item[field] = (
                    [part.strip() for part in value.split(",") if part.strip()]
                    if isinstance(value, str)
                    else list(_string_sequence(value, where=f"{path}.{field}"))
                )
        models: dict[str, str] = {}
        if frontmatter.get("model") is not None:
            if not isinstance(frontmatter["model"], str):
                raise ProfileSourceError(f"{path}.model must be a string")
            models["claude"] = frontmatter["model"]
        if frontmatter.get("models") is not None:
            models.update(_string_mapping(frontmatter["models"], where=f"{path}.models"))
        if models:
            item["models"] = models
        _validate_item_fields(item, where=f"plugin {plugin!r} agent {path.name!r}")
        _validate_item_paths(
            item,
            source_root=source_root,
            source_dir=payload_root,
            where=f"plugin {plugin!r} agent {path.name!r}",
        )
        _stamp_plugin_native(item, native)
        out.append(item)
    return out


def _plugin_skills(
    plugin: str,
    payload_root: Path,
    source_root: Path,
    requested: Sequence[str],
    native: set[str],
    context: str,
) -> list[dict[str, Any]]:
    skills_root = resolve_within(
        source_root, payload_root / "skills", kind=f"plugin {plugin!r} skills"
    )
    if not skills_root.is_dir():
        return []
    harnesses = _plugin_effective_harnesses(requested, _PLUGIN_SKILL_HARNESSES, native)
    out: list[dict[str, Any]] = []
    for path in sorted(skills_root.iterdir(), key=lambda item: item.name):
        path = resolve_within(source_root, path, kind=f"plugin {plugin!r} skill")
        if not path.is_dir():
            continue
        body = resolve_within(source_root, path / "SKILL.md", kind=f"plugin {plugin!r} skill body")
        if not body.is_file():
            continue
        item = {
            "name": path.name,
            "path": f"skills/{path.name}",
            "harnesses": harnesses,
            "_source_dir": str(payload_root),
            "_source_context": f"{context}:skills[{path.name!r}]",
        }
        _validate_item_fields(item, where=f"plugin {plugin!r} skill {path.name!r}")
        _validate_item_paths(
            item,
            source_root=source_root,
            source_dir=payload_root,
            where=f"plugin {plugin!r} skill {path.name!r}",
        )
        _stamp_plugin_native(item, native)
        out.append(item)
    return out


def _plugin_hook_script(
    command: object,
    payload_root: Path,
    source_root: Path,
    *,
    plugin: str,
    manifest: Path,
) -> str | None:
    if not isinstance(command, str) or not command:
        raise ProfileSourceError(f"plugin {plugin!r} hook in {manifest} is missing command")
    prefix = "${CLAUDE_PLUGIN_ROOT}/"
    if command.startswith(prefix):
        relative = command.removeprefix(prefix)
    elif Path(command).is_absolute():
        hooks_root = resolve_within(
            source_root, payload_root / "hooks", kind=f"plugin {plugin!r} hooks"
        )
        candidate = resolve_within(
            source_root, Path(command), kind=f"plugin {plugin!r} hook command"
        )
        try:
            relative = PurePosixPath(*candidate.relative_to(payload_root).parts).as_posix()
        except ValueError:
            return None
        if not candidate.is_file() or not candidate.is_relative_to(hooks_root):
            return None
    else:
        relative = command
    try:
        validate_relative_path(relative, kind=f"plugin {plugin!r} hook script")
    except ProfileSourceError:
        return None
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] != "hooks":
        return None
    candidate = resolve_within(
        source_root, payload_root.joinpath(*parts), kind=f"plugin {plugin!r} hook script"
    )
    if not candidate.is_file():
        if command.startswith(prefix) or relative.startswith("hooks/"):
            raise ProfileSourceError(f"plugin {plugin!r} hook script was not found: {candidate}")
        return None
    return PurePosixPath(*parts).as_posix()


def _plugin_hooks(
    plugin: str,
    payload_root: Path,
    source_root: Path,
    requested: Sequence[str],
    native: set[str],
    context: str,
) -> list[dict[str, Any]]:
    manifest = resolve_within(
        source_root,
        payload_root / ".claude-plugin" / "plugin.json",
        kind=f"plugin {plugin!r} manifest",
    )
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProfileSourceError(f"plugin {plugin!r} manifest is invalid: {exc}") from exc
    if not isinstance(data, Mapping):
        raise ProfileSourceError(f"plugin {plugin!r} manifest must be a mapping")
    hooks = data.get("hooks", {})
    if not isinstance(hooks, Mapping):
        raise ProfileSourceError(f"plugin {plugin!r} manifest hooks must be a mapping")
    script_harnesses = _plugin_effective_harnesses(requested, _PLUGIN_HOOK_HARNESSES, native)
    command_harnesses = _plugin_effective_harnesses(
        requested, _PLUGIN_COMMAND_HOOK_HARNESSES, native
    )
    out: list[dict[str, Any]] = []
    for event, entries in hooks.items():
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
            raise ProfileSourceError(f"plugin {plugin!r} hooks[{event!r}] must be a list")
        for outer_index, outer in enumerate(entries):
            if not isinstance(outer, Mapping):
                raise ProfileSourceError(f"plugin {plugin!r} hook entry must be a mapping")
            inner_hooks = outer.get("hooks", ())
            if not isinstance(inner_hooks, Sequence) or isinstance(
                inner_hooks, (str, bytes, bytearray)
            ):
                raise ProfileSourceError(f"plugin {plugin!r} hook hooks must be a list")
            for inner_index, inner in enumerate(inner_hooks):
                if not isinstance(inner, Mapping) or inner.get("type") != "command":
                    continue
                command = inner.get("command")
                script = _plugin_hook_script(
                    command, payload_root, source_root, plugin=plugin, manifest=manifest
                )
                harnesses = script_harnesses if script else command_harnesses
                if not harnesses:
                    continue
                item: dict[str, Any] = {
                    "name": f"{plugin}-{event}-{outer_index}-{inner_index}",
                    "event": event,
                    "harnesses": harnesses,
                    "_source_dir": str(payload_root),
                    "_source_context": f"{context}:hooks[{event!r}]",
                }
                if script:
                    item["script"] = script
                else:
                    item["command"] = command
                if outer.get("matcher") is not None:
                    item["matcher"] = outer["matcher"]
                for field in ("timeout", "async"):
                    if inner.get(field) is not None:
                        item[field] = inner[field]
                _validate_item_fields(item, where=f"plugin {plugin!r} hook {event!r}")
                _validate_item_paths(
                    item,
                    source_root=source_root,
                    source_dir=payload_root,
                    where=f"plugin {plugin!r} hook {event!r}",
                )
                _stamp_plugin_native(item, native)
                out.append(item)
    return out


def _plugin_items(
    path: Path,
    *,
    source_root: Path,
    environment: Mapping[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """Expand local plugin payloads into renderer primitives and native records."""
    data = _load_yaml_mapping(path)
    plugins = data.get("plugins", {})
    if not isinstance(plugins, Mapping):
        raise ProfileSourceError(f"plugins registry {path} field 'plugins' must be a mapping")
    out = {section: [] for section in (*_ITEM_SECTIONS, "native_plugins")}
    for name, raw in plugins.items():
        validate_name(name, kind="plugin registry name")
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ProfileSourceError(f"plugins registry {path} entry {name!r} must be a mapping")
        _reject_unknown_keys(
            raw, allowed=_PLUGIN_KEYS, where=f"plugins registry {path} entry {name!r}"
        )
        body = dict(raw)
        if "name" in body and body["name"] != name:
            raise ProfileSourceError(
                f"plugins registry {path} entry {name!r} has conflicting item name {body['name']!r}"
            )
        for key in ("path", "git", "branch"):
            if key in body and (not isinstance(body[key], str) or not body[key]):
                raise ProfileSourceError(
                    f"plugins registry {path} entry {name!r} field {key!r} "
                    "must be a non-empty string"
                )
        local_path = body.get("path")
        git_source = body.get("git")
        if local_path is not None:
            marketplace_root = resolve_declared_path(
                source_root, local_path, kind=f"plugin {name!r} path"
            )
            plugin_boundary = source_root
        elif git_source is not None:
            home = environment.get("HOME")
            if not isinstance(home, str) or not home:
                raise ProfileSourceError(
                    f"git plugin {name!r} requires HOME in the supplied environment"
                )
            home_path = Path(home)
            if not home_path.is_absolute():
                raise ProfileSourceError(f"git plugin {name!r} requires an absolute HOME path")
            marketplace_root = (home_path / ".cache" / "cheese-flow" / "plugins" / name).resolve(
                strict=False
            )
            plugin_boundary = marketplace_root
        else:
            raise ProfileSourceError(
                f"plugins registry {path} entry {name!r} requires a local path or git source"
            )
        if not marketplace_root.is_dir():
            raise ProfileSourceError(f"plugin {name!r} path is not a directory: {marketplace_root}")
        native = _plugin_native_harnesses(
            body, name=name, where=f"plugins registry {path} entry {name!r}"
        )
        marketplace_json = resolve_within(
            plugin_boundary,
            marketplace_root / ".claude-plugin" / "marketplace.json",
            kind=f"plugin {name!r} marketplace",
        )
        if not marketplace_json.is_file():
            raise ProfileSourceError(
                f"plugin {name!r} marketplace.json was not found: {marketplace_json}"
            )
        try:
            marketplace = json.loads(marketplace_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProfileSourceError(f"plugin {name!r} marketplace.json is invalid: {exc}") from exc
        if not isinstance(marketplace, Mapping):
            raise ProfileSourceError(f"plugin {name!r} marketplace.json must be a mapping")
        marketplace_name = marketplace.get("name") or body.get("marketplace_name") or name
        if not isinstance(marketplace_name, str) or not marketplace_name:
            raise ProfileSourceError(f"plugin {name!r} marketplace name must be a string")
        metadata = marketplace.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, Mapping):
            raise ProfileSourceError(f"plugin {name!r} marketplace metadata must be a mapping")
        payload_base = marketplace_root
        if metadata.get("pluginRoot"):
            payload_base = _resolve_plugin_relative(
                marketplace_root,
                metadata["pluginRoot"],
                source_root=plugin_boundary,
                kind="metadata.pluginRoot",
                plugin=name,
            )
        entries = marketplace.get("plugins", ())
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes, bytearray)):
            raise ProfileSourceError(f"plugin {name!r} marketplace plugins must be a list")
        matched = False
        servers: list[str] = []
        requested = list(
            _string_sequence(
                body["harnesses"], where=f"plugins registry {path} entry {name!r}.harnesses"
            )
            if "harnesses" in body
            else ()
        )
        for entry in entries:
            if not isinstance(entry, Mapping) or entry.get("name") != name:
                continue
            matched = True
            payload_root = _resolve_plugin_relative(
                payload_base,
                entry.get("source", ""),
                source_root=plugin_boundary,
                kind="source",
                plugin=name,
            )
            if not payload_root.is_dir():
                raise ProfileSourceError(
                    f"plugin {name!r} payload is not a directory: {payload_root}"
                )
            mcp_path = resolve_within(
                plugin_boundary,
                payload_root / ".mcp.json",
                kind=f"plugin {name!r} MCP manifest",
            )
            if mcp_path.is_file():
                try:
                    mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ProfileSourceError(
                        f"plugin {name!r} .mcp.json is invalid: {exc}"
                    ) from exc
                if not isinstance(mcp_data, Mapping):
                    raise ProfileSourceError(f"plugin {name!r} .mcp.json must be a mapping")
                servers_data = mcp_data.get("mcpServers", {})
                if not isinstance(servers_data, Mapping):
                    raise ProfileSourceError(
                        f"plugin {name!r} .mcp.json mcpServers must be a mapping"
                    )
                for server_name, server_body in servers_data.items():
                    validate_name(server_name, kind=f"plugin {name!r} MCP name")
                    if not isinstance(server_body, Mapping):
                        raise ProfileSourceError(
                            f"plugin {name!r} MCP {server_name!r} must be a mapping"
                        )
                    item = dict(server_body)
                    item["name"] = server_name
                    item["_source_dir"] = str(payload_root)
                    item["_source_context"] = (
                        f"{path}:plugins[{name!r}].mcpServers[{server_name!r}]"
                    )
                    if "env" in item:
                        env = _string_mapping(
                            item["env"], where=f"plugin {name!r} MCP {server_name!r}.env"
                        )
                        for value in env.values():
                            for match in _ENV_REF_RE.finditer(value):
                                variable = match.group(1) or match.group(2)
                                if variable not in environment and not item.get("optional"):
                                    raise ProfileSourceError(
                                        f"plugin {name!r} MCP {server_name!r} references unset "
                                        f"environment variable {variable!r}"
                                    )
                        item["env"] = env
                    item["harnesses"] = (
                        _plugin_effective_harnesses(requested, _PLUGIN_MCP_HARNESSES, native)
                        if requested
                        else []
                    )
                    if not requested:
                        item.pop("harnesses", None)
                    if body.get("gate_unless") is not None:
                        item["gate_unless"] = body["gate_unless"]
                    _validate_item_fields(item, where=f"plugin {name!r} MCP {server_name!r}")
                    _stamp_plugin_native(item, native)
                    out["mcps"].append(item)
                    servers.append(server_name)
            out["skills"].extend(
                _plugin_skills(name, payload_root, plugin_boundary, requested, native, str(path))
            )
            out["agents"].extend(
                _plugin_agents(name, payload_root, plugin_boundary, requested, native, str(path))
            )
            out["hooks"].extend(
                _plugin_hooks(name, payload_root, plugin_boundary, requested, native, str(path))
            )
        if not matched:
            raise ProfileSourceError(
                f"plugin {name!r} has no matching plugins[] entry in {marketplace_json}"
            )
        if native:
            out["native_plugins"].append(
                {
                    "name": name,
                    "claude_native": "claude" in native,
                    "codex_native": "codex" in native,
                    "copilot_native": "copilot" in native,
                    "servers": servers,
                    "marketplace_root": str(marketplace_root),
                    "marketplace_name": marketplace_name,
                    "description": body.get("description") or "",
                    "_source_context": f"{path}:plugins[{name!r}]",
                }
            )
    _validate_unique_items(out)
    return out


def _registry_paths(value: Any, *, section: str) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, (str, bytes, bytearray, Path)):
        return list(_string_sequence(value, where=f"registries.{section}"))
    if isinstance(value, (str, Path)):
        return [value]
    raise ProfileSourceError(f"registries.{section} must be a relative path")


def _expand_registries(
    directive: Any,
    *,
    source_root: Path,
    environment: Mapping[str, str],
) -> dict[str, list[dict[str, Any]]]:
    if directive is None:
        return {section: [] for section in (*_ITEM_SECTIONS, "native_plugins")}
    registries = _as_mapping(directive, where="registries")
    _reject_unknown_keys(registries, allowed=_REGISTRY_KEYS, where="registries")
    out = {section: [] for section in (*_ITEM_SECTIONS, "native_plugins")}
    for section in ("mcps", "agents", "hooks"):
        for raw_path in _registry_paths(registries.get(section), section=section):
            path = resolve_declared_path(source_root, raw_path, kind=f"registries.{section}")
            if not path.is_file():
                raise ProfileSourceError(f"declared registry was not found: {path}")
            out[section].extend(_registry_items(path, section=section, source_root=source_root))
    for raw_path in _registry_paths(registries.get("skills"), section="skills"):
        path = resolve_declared_path(source_root, raw_path, kind="registries.skills")
        out["skills"].extend(
            _external_skill_items(path, source_root=source_root)
            if path.is_file()
            else _local_skill_items(path, source_root=source_root)
        )
    for raw_path in _registry_paths(registries.get("plugins"), section="plugins"):
        path = resolve_declared_path(source_root, raw_path, kind="registries.plugins")
        if not path.is_file():
            raise ProfileSourceError(f"declared registry was not found: {path}")
        expanded = _plugin_items(path, source_root=source_root, environment=environment)
        for section, items in expanded.items():
            out[section].extend(items)
    _validate_unique_items(out)
    return out


def _substitute(value: str, environment: Mapping[str, str], *, where: str) -> str:
    def replace(match: re.Match[str]) -> str:
        variable = match.group(1) or match.group(2)
        if variable not in environment:
            raise ProfileSourceError(f"{where} references unset environment variable {variable!r}")
        return str(environment[variable])

    return _ENV_REF_RE.sub(replace, value)


def _resolve_template(value: str, environment: Mapping[str, str], *, where: str) -> str:
    expanded = _substitute(value, environment, where=where)
    if "{{" not in expanded:
        return expanded
    from .rendering.template import render_value

    try:
        return render_value(expanded, "profile", environment=environment)
    except ValueError as exc:
        raise ProfileSourceError(f"{where} has an invalid template: {exc}") from exc


def _resolve_declared_environment(
    raw: Any, *, environment: Mapping[str, str], where: str
) -> dict[str, str]:
    declared = _string_mapping(raw, where=where)
    available = _template_environment(environment)
    resolved: dict[str, str] = {}
    for key, value in declared.items():
        expanded = _ENV_REF_RE.sub(
            lambda match: str(available.get(match.group(1) or match.group(2), match.group(0))),
            value,
        )
        if "{{" in expanded:
            resolved_value = _resolve_template(
                expanded, {**available, **resolved}, where=f"{where}[{key!r}]"
            )
        else:
            resolved_value = expanded
        resolved[key] = resolved_value
    return resolved


def _compile_targets(
    raw: Any, *, environment: Mapping[str, str], where: Path
) -> tuple[CompileTarget, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Mapping):
        raise ProfileSourceError(f"{where} compile_targets must be a mapping")
    targets: list[CompileTarget] = []
    owners: dict[str, str] = {}
    for name, config in raw.items():
        validate_name(name, kind="compile target name")
        if not isinstance(config, Mapping):
            raise ProfileSourceError(f"compile target {name!r} must be a mapping")
        _reject_unknown_keys(
            config,
            allowed=_COMPILE_TARGET_KEYS,
            where=f"compile target {name!r}",
        )
        symbolic_root = config.get("target_root")
        if not isinstance(symbolic_root, str) or not symbolic_root:
            raise ProfileSourceError(f"compile target {name!r} requires target_root")
        expanded = _resolve_template(symbolic_root, environment, where=f"compile target {name!r}")
        resolved_root = Path(expanded)
        if not resolved_root.is_absolute():
            raise ProfileSourceError(f"compile target {name!r} target_root must resolve absolute")
        harnesses = config.get("harnesses")
        if harnesses is None:
            raise ProfileSourceError(f"compile target {name!r} harnesses must be a non-empty list")
        normalized = _string_sequence(harnesses, where=f"compile target {name!r} harnesses")
        if not normalized:
            raise ProfileSourceError(f"compile target {name!r} harnesses must be a non-empty list")
        for harness in normalized:
            if harness not in _COMPILE_HARNESSES:
                raise ProfileSourceError(f"compile target {name!r} has unknown harness {harness!r}")
            if harness in owners:
                raise ProfileSourceError(
                    f"compile target {name!r} duplicates harness {harness!r} "
                    f"already owned by {owners[harness]!r}"
                )
            owners[harness] = name
        try:
            targets.append(
                CompileTarget(
                    name=name,
                    symbolic_root=symbolic_root,
                    resolved_root=resolved_root.resolve(strict=False),
                    harnesses=normalized,
                )
            )
        except ValidationError as exc:
            raise ProfileSourceError(f"invalid compile target {name!r}: {exc}") from exc
    return tuple(targets)


def _merge_settings(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(left))
    for key, value in right.items():
        if isinstance(merged.get(key), Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_settings(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    for key in ("permissions_allow", "permissions_deny"):
        if key not in merged:
            continue
        values = _string_sequence(merged[key], where=f"settings.{key}")
        values = sorted(set(values))
        merged[key] = values
    return merged


def _merge(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        section: [*left.get(section, ()), *right.get(section, ())]
        for section in (*_ITEM_SECTIONS, "native_plugins")
    }
    merged["settings"] = _merge_settings(
        left.get("settings", {}),
        right.get("settings", {}),
    )
    _validate_unique_items(merged)
    return merged


def _parse_one(
    profile_dir: Path,
    *,
    source_root: Path,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    manifest_path = resolve_profile_file(source_root, profile_dir, "profile.yaml")
    raw = _load_yaml_mapping(manifest_path)
    _reject_unknown_keys(raw, allowed=_PROFILE_KEYS, where=str(manifest_path))
    name = _validate_profile_identity(
        profile_dir,
        raw.get("name"),
        manifest_path=manifest_path,
    )

    includes = (
        list(_string_sequence(raw["include"], where=f"{manifest_path}.include"))
        if "include" in raw
        else []
    )
    for include in includes:
        validate_name(include, kind="include name")

    sections = _EMPTY_SECTIONS.copy()
    for section in _ITEM_SECTIONS:
        if section in raw and raw[section] is None:
            raise ProfileSourceError(f"{manifest_path}.{section} must be a YAML list")
        sections[section] = _decorate_items(
            raw.get(section),
            source_root=source_root,
            source_dir=profile_dir,
            where=f"{manifest_path}.{section}",
        )
    template_environment = _template_environment(environment)
    registries = _expand_registries(
        raw.get("registries"),
        source_root=source_root,
        environment=template_environment,
    )
    for section in _ITEM_SECTIONS:
        sections[section] = registries[section] + sections[section]
    sections["native_plugins"] = registries["native_plugins"]
    _validate_unique_items(sections)

    if "compile_targets" in raw and raw["compile_targets"] is None:
        raise ProfileSourceError(f"{manifest_path}.compile_targets must be a YAML mapping")
    compile_targets = _compile_targets(
        raw.get("compile_targets"), environment=template_environment, where=manifest_path
    )

    if "description" in raw and not isinstance(raw["description"], str):
        raise ProfileSourceError(f"{manifest_path} description must be a string")
    description = raw.get("description", "")
    if "isolated" in raw:
        isolated = _boolean(raw["isolated"], where=f"{manifest_path}.isolated")
    else:
        isolated = False
    if (
        "system_prompt" in raw
        and raw["system_prompt"] is not None
        and not isinstance(raw["system_prompt"], str)
    ):
        raise ProfileSourceError(f"{manifest_path}.system_prompt must be a string")
    system_prompt = raw.get("system_prompt")
    if system_prompt:
        prompt_path = resolve_declared_path(
            profile_dir, system_prompt, kind=f"{manifest_path}.system_prompt"
        )
        if not prompt_path.is_file():
            raise ProfileSourceError(
                f"{manifest_path}.system_prompt is not a regular file: {prompt_path}"
            )
        system_prompt = str(prompt_path)

    settings = _settings_mapping(raw.get("settings", {}), where=f"{manifest_path}.settings")
    tools = _field_string_sequence(raw, "tools", where=str(manifest_path))
    permissions_deny = _field_string_sequence(raw, "permissions_deny", where=str(manifest_path))
    permissions_allow = _field_string_sequence(raw, "permissions_allow", where=str(manifest_path))
    enabled_plugins = (
        _boolean_mapping(raw["enabled_plugins"], where=f"{manifest_path}.enabled_plugins")
        if "enabled_plugins" in raw
        else {}
    )
    env = (
        _resolve_declared_environment(
            raw["env"],
            environment=environment,
            where=f"{manifest_path}.env",
        )
        if "env" in raw
        else {}
    )
    extra_args = _field_string_sequence(raw, "extra_args", where=str(manifest_path))
    if (
        "target_default" in raw
        and raw["target_default"] is not None
        and not isinstance(raw["target_default"], str)
    ):
        raise ProfileSourceError(f"{manifest_path}.target_default must be a string")
    target_default = raw.get("target_default")
    if target_default == "":
        target_default = None
    marketplaces = (
        _string_mapping(raw["marketplaces"], where=f"{manifest_path}.marketplaces")
        if "marketplaces" in raw
        else {}
    )
    mcp_scope = raw.get("mcp_scope", "plugin")
    if not isinstance(mcp_scope, str) or mcp_scope not in ("plugin", "user"):
        raise ProfileSourceError(f"{manifest_path} has invalid mcp_scope {mcp_scope!r}")
    return {
        "name": name,
        "description": description,
        "include": includes,
        **sections,
        "settings": settings,
        "isolated": isolated,
        "system_prompt": system_prompt,
        "tools": tools,
        "permissions_deny": permissions_deny,
        "permissions_allow": permissions_allow,
        "enabled_plugins": enabled_plugins,
        "env": env,
        "extra_args": extra_args,
        "target_default": target_default,
        "marketplaces": marketplaces,
        "mcp_scope": mcp_scope,
        "compile_targets": compile_targets,
    }


def parse_one(
    profile_dir: Path,
    *,
    source_root: Path | None = None,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Parse one profile YAML and its declared registries without includes."""
    profile_dir = Path(profile_dir)
    root = validate_explicit_source_root(
        source_root if source_root is not None else profile_dir.parent.parent
    )
    profile_dir = resolve_within(root, profile_dir, kind="profile directory")
    if not profile_dir.is_dir():
        raise ProfileSourceError(f"profile directory was not found: {profile_dir}")
    resolved_environment = (
        _string_mapping(environment, where="environment") if environment is not None else {}
    )
    return _parse_one(profile_dir, source_root=root, environment=resolved_environment)


def _parse_graph(
    profile_dir: Path,
    *,
    source_root: Path,
    environment: Mapping[str, str],
    stack: tuple[Path, ...],
) -> dict[str, Any]:
    canonical = resolve_within(source_root, profile_dir, kind="profile directory")
    if canonical in stack:
        raise ProfileSourceError(f"include cycle detected at {canonical}")
    current = _parse_one(canonical, source_root=source_root, environment=environment)
    merged: dict[str, Any] = {section: [] for section in (*_ITEM_SECTIONS, "native_plugins")}
    merged["settings"] = {}
    for include in current["include"]:
        included_dir = resolve_profile_dir(source_root, include)
        merged = _merge(
            merged,
            _parse_graph(
                included_dir,
                source_root=source_root,
                environment=environment,
                stack=(*stack, canonical),
            ),
        )
    merged = _merge(merged, current)
    for field_name in (
        "name",
        "description",
        "isolated",
        "system_prompt",
        "tools",
        "permissions_deny",
        "permissions_allow",
        "enabled_plugins",
        "env",
        "extra_args",
        "target_default",
        "marketplaces",
        "mcp_scope",
        "compile_targets",
    ):
        merged[field_name] = current[field_name]
    return merged


def resolve_profile(
    source_root: Path, profile_name: str, *, environment: Mapping[str, str]
) -> ResolvedProfile:
    root = validate_explicit_source_root(source_root)
    resolved_environment = _string_mapping(environment, where="environment")
    profile_dir = resolve_profile_dir(root, profile_name)
    merged = _parse_graph(profile_dir, source_root=root, environment=resolved_environment, stack=())
    merged["source_id"] = source_id(root, profile_dir)
    try:
        profile = ResolvedProfile.model_validate(merged)
        template_environment = {
            **_template_environment(resolved_environment),
            **dict(profile.env),
        }
        object.__setattr__(profile, "_template_environment", MappingProxyType(template_environment))
        return profile
    except ValidationError as exc:
        raise ProfileSourceError(f"invalid resolved profile {profile_name!r}: {exc}") from exc
