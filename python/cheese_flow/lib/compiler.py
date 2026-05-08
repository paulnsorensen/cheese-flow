"""Port of `src/lib/compiler.ts` — compile portable agent + skill sources.

Eta → Jinja2 translation strategy: the TS pipeline uses Eta with
``autoEscape: false, autoTrim: false, useWith: true``. The templates only
combine three syntactic features — ``<%= expr %>`` outputs, literal text, and
``forEach`` block loops — so we preprocess the template source into Jinja2
syntax (`{{ expr }}` outputs, `{% for v in xs %}` / `{% endfor %}` blocks)
and render with ``Environment(autoescape=False, trim_blocks=False,
lstrip_blocks=False)`` to keep whitespace identical.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from jinja2 import Environment
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from cheese_flow.adapters import HARNESS_ADAPTERS
from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.harness import (
    AgentArtifactInput,
    HarnessAdapter,
    HarnessName,
    HooksSource,
    ManifestComponentPaths,
    PluginMetadata,
    SurfaceEmissionResult,
)
from cheese_flow.lib.model_manifest import (
    ModelManifest,
    apply_model_manifest,
    read_model_manifest,
)
from cheese_flow.lib.schemas import (
    AgentFrontmatter,
    SkillFrontmatter,
    parse_agent_frontmatter,
    parse_command_frontmatter,
    parse_skill_frontmatter,
    resolve_model,
)

DEFAULT_PLUGIN_METADATA: PluginMetadata = {
    "name": "cheese-flow",
    "version": "0.1.0",
    "description": (
        "Opinionated coding harness plugin scaffold for portable agents and skills."
    ),
    "author": {"name": "Paul Sorensen"},
    "license": "MIT",
    "repository": "https://github.com/paulnsorensen/cheese-flow",
}

_FOREACH_OPEN = re.compile(
    r"<%\s*([\w.]+)\.forEach\(\s*function\s*\(\s*(\w+)\s*\)\s*\{\s*%>"
)
_FOREACH_CLOSE = re.compile(r"<%\s*\}\)\s*%>")
_OUTPUT_TAG = re.compile(r"<%=\s*(.*?)\s*%>", re.DOTALL)


def _eta_to_jinja(src: str) -> str:
    """Translate an Eta template body into a Jinja2-compatible source string."""
    src = _FOREACH_CLOSE.sub("{% endfor %}", src)
    src = _FOREACH_OPEN.sub(r"{% for \2 in \1 %}", src)
    src = _OUTPUT_TAG.sub(r"{{ \1 }}", src)
    return src


_JINJA_ENV = Environment(
    autoescape=False,
    trim_blocks=False,
    lstrip_blocks=False,
    keep_trailing_newline=True,
)


_NODE_YAML_LINE_WIDTH = 80


def _fold_flow_value(value: str, indent: str, indent_at_start: int) -> str:
    """Port of Node ``yaml@2``'s ``foldFlowLines`` for plain scalars.

    Mirrors the algorithm from ``foldFlowLines.js``: ``indent_at_start`` is the
    column already consumed by the key prefix (``"name: "`` etc.), and
    determines how much room remains on the first line.
    """
    indent_length = len(indent)
    limit = _NODE_YAML_LINE_WIDTH - indent_length
    if len(value) <= limit:
        return value
    end_step = max(1 + 20, 1 + _NODE_YAML_LINE_WIDTH - indent_length)
    folds: list[int] = []
    end = _NODE_YAML_LINE_WIDTH - indent_at_start
    split: int | None = None
    prev: str | None = None

    for i, ch in enumerate(value):
        if (
            ch == " "
            and prev is not None
            and prev not in (" ", "\n", "\t")
            and i + 1 < len(value)
            and value[i + 1] not in (" ", "\n", "\t")
        ):
            split = i
        if i >= end and split is not None:
            folds.append(split)
            end = split + end_step
            split = None
        prev = ch

    if not folds:
        return value

    parts = [value[: folds[0]]]
    for idx, fold in enumerate(folds):
        next_fold = folds[idx + 1] if idx + 1 < len(folds) else len(value)
        parts.append(f"\n{indent}{value[fold + 1:next_fold]}")
    return "".join(parts)


_RESERVED_SCALARS: frozenset[str] = frozenset(
    {"true", "false", "null", "True", "False", "Null", "TRUE", "FALSE", "NULL", "~"}
)


def _needs_quoting(value: str) -> bool:
    """Return True when ``value`` cannot be emitted as a plain YAML scalar."""
    if value == "":
        return True
    if value != value.strip():
        return True
    if value[0] in "!&*-?,[]{}>|%@`'\"#":
        return True
    if value[0] == ":" or value[0].isdigit():
        return True
    if ": " in value or " #" in value:
        return True
    return value in _RESERVED_SCALARS


def _stringify_scalar(value: str, indent: str, indent_at_start: int) -> str:
    if _needs_quoting(value):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return _fold_flow_value(value, indent, indent_at_start)


def _stringify_yaml(data: dict[str, Any]) -> str:
    """Hand-rolled Node ``yaml@2`` plain-style emitter for agent frontmatter.

    The TS pipeline calls ``yaml.stringify`` with default options
    (``lineWidth: 80``, ``indent: 2``); ruamel.yaml's wrapping algorithm
    produces visibly different output for medium-length descriptions, so the
    Python compiler reimplements only the subset needed for agent + skill
    frontmatter dumps (string / list-of-strings / nested dict values).
    """
    return _emit_mapping(data, indent_level=0)


def _emit_mapping(mapping: dict[str, Any], *, indent_level: int) -> str:
    indent = "  " * indent_level
    fold_indent = "  " * (indent_level + 1)
    lines: list[str] = []
    for key, value in mapping.items():
        prefix_length = len(indent) + len(str(key)) + 2  # "key: "
        if isinstance(value, str):
            scalar = _stringify_scalar(value, fold_indent, prefix_length)
            lines.append(f"{indent}{key}: {scalar}")
        elif isinstance(value, list):
            if len(value) == 0:
                lines.append(f"{indent}{key}: []")
            else:
                lines.append(f"{indent}{key}:")
                for item in value:
                    lines.append(_emit_list_item(item, indent_level=indent_level + 1))
        elif isinstance(value, dict):
            lines.append(f"{indent}{key}:")
            lines.append(_emit_mapping(value, indent_level=indent_level + 1))
        elif isinstance(value, bool):
            lines.append(f"{indent}{key}: {'true' if value else 'false'}")
        elif value is None:
            lines.append(f"{indent}{key}: null")
        else:
            lines.append(f"{indent}{key}: {value}")
    return "\n".join(lines) + "\n"


def _emit_list_item(item: Any, *, indent_level: int) -> str:
    indent = "  " * indent_level
    fold_indent = "  " * (indent_level + 1)
    item_indent_at_start = len(indent) + 2  # "- "
    if isinstance(item, str):
        scalar = _stringify_scalar(item, fold_indent, item_indent_at_start)
        return f"{indent}- {scalar}"
    if isinstance(item, dict):
        # Mirror Node yaml's "-\n  key: value" expansion for nested mappings.
        rendered = _emit_mapping(item, indent_level=indent_level + 1).rstrip("\n")
        return f"{indent}-\n{rendered}"
    return f"{indent}- {item}"


def _dump_json(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _trim_start(value: str) -> str:
    return value.lstrip()


def _build_agent_file(
    frontmatter: AgentFrontmatter,
    adapter: HarnessAdapter,
    resolved_model: str,
    rendered_body: str,
) -> str:
    raw_fields = frontmatter.model_dump(by_alias=True, exclude_none=True)
    artifact = adapter.buildAgentArtifact(
        AgentArtifactInput(frontmatter=raw_fields, resolvedModel=resolved_model)
    )
    return (
        f"---\n{_stringify_yaml(artifact.frontmatter)}---\n"
        f"{_trim_start(rendered_body)}{artifact.appendix}"
    )


_NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class _PluginAuthorModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: _NonEmptyStr
    email: str | None = None
    url: str | None = None


class _PluginMetadataModel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: _NonEmptyStr
    version: _NonEmptyStr
    description: _NonEmptyStr
    author: _PluginAuthorModel
    license: _NonEmptyStr
    repository: _NonEmptyStr
    homepage: str | None = None
    keywords: list[str] | None = Field(default=None)


def _read_plugin_metadata(project_root: Path) -> PluginMetadata:
    plugin_json = project_root / ".claude-plugin" / "plugin.json"
    if not plugin_json.exists():
        return DEFAULT_PLUGIN_METADATA
    raw = plugin_json.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    return _validate_plugin_metadata(parsed)


def _validate_plugin_metadata(parsed: Any) -> PluginMetadata:
    try:
        validated = _PluginMetadataModel.model_validate(parsed)
    except ValidationError as error:
        raise ValueError(
            f"Plugin metadata validation failed: {error}"
        ) from error
    return validated.model_dump(exclude_none=True)  # type: ignore[return-value]


def _read_hooks_source(project_root: Path) -> HooksSource:
    hooks_path = project_root / "hooks.json"
    if not hooks_path.exists():
        return {}
    raw = hooks_path.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("hooks.json must contain an object at the top level.")
    return parsed  # type: ignore[return-value]


@dataclass(frozen=True)
class CompiledHarnessBundle:
    harness: HarnessName
    outputRoot: str
    pluginMetadata: PluginMetadata


@dataclass(frozen=True)
class _CompileSession:
    projectRoot: Path
    pluginMetadata: PluginMetadata
    hooksSource: HooksSource
    skillSourceDirectory: Path
    modelManifest: ModelManifest | None


def _create_compile_session(project_root: Path) -> _CompileSession:
    return _CompileSession(
        projectRoot=project_root,
        pluginMetadata=_read_plugin_metadata(project_root),
        modelManifest=read_model_manifest(project_root),
        hooksSource=_read_hooks_source(project_root),
        skillSourceDirectory=project_root / "skills",
    )


async def compile_harness_bundle(
    *, project_root: str | Path, harness: HarnessName
) -> CompiledHarnessBundle:
    session = _create_compile_session(Path(project_root))
    return await _compile_harness_bundle_from_session(session, harness)


async def compile_harness_bundles(
    *, project_root: str | Path, harnesses: Iterable[HarnessName]
) -> list[str]:
    session = _create_compile_session(Path(project_root))
    outputs: list[str] = []
    for harness_name in harnesses:
        compiled = await _compile_harness_bundle_from_session(session, harness_name)
        outputs.append(compiled.outputRoot)
    return outputs


async def _clean_generated_artifacts(adapter: HarnessAdapter, output_root: Path) -> None:
    generated_dirs = [
        adapter.agentDirectory,
        adapter.skillDirectory,
        adapter.commandDirectory,
        adapter.manifestDir,
    ]
    if adapter.emitSurface is not None:
        generated_dirs.extend(["rules", "commands"])

    generated_files = [adapter.mcpFileName, "manifest.json"]
    if adapter.buildHookConfig({}) is not None:
        generated_files.append("hooks.json")

    async def _remove_dir(name: str) -> None:
        path = output_root / name
        if path.is_symlink() or path.exists():
            await asyncio.to_thread(shutil.rmtree, path, ignore_errors=True)

    async def _remove_file(name: str) -> None:
        path = output_root / name
        if path.is_symlink() or path.exists():
            with contextlib.suppress(FileNotFoundError):
                await asyncio.to_thread(path.unlink)

    await asyncio.gather(
        *[_remove_dir(name) for name in generated_dirs if name is not None],
        *[_remove_file(name) for name in generated_files],
    )


def _manifest_directory_path(relative_path: str) -> str:
    return f"./{relative_path}/"


def _manifest_file_path(relative_path: str) -> str:
    return f"./{relative_path}"


def _build_manifest_component_paths(
    *,
    adapter: HarnessAdapter,
    agents: list[str],
    skills: list[str],
    commands: list[str],
    emitted_surface: SurfaceEmissionResult,
) -> ManifestComponentPaths:
    paths: ManifestComponentPaths = {}
    if len(agents) > 0:
        paths["agents"] = _manifest_directory_path(adapter.agentDirectory)
    if len(skills) > 0:
        paths["skills"] = _manifest_directory_path(adapter.skillDirectory)
    if len(commands) > 0 and adapter.commandDirectory is not None:
        if adapter.name == "codex":
            paths["apps"] = _manifest_directory_path(adapter.commandDirectory)
        else:
            paths["commands"] = _manifest_directory_path(adapter.commandDirectory)
    if len(emitted_surface["rules"]) > 0:
        paths["rules"] = _manifest_directory_path("rules")
    if len(emitted_surface["commands"]) > 0:
        paths["commands"] = _manifest_directory_path("commands")
    if adapter.buildHookConfig({}) is not None:
        paths["hooks"] = _manifest_file_path("hooks.json")
    paths["mcpServers"] = _manifest_file_path(adapter.mcpFileName)
    return paths


async def _compile_harness_bundle_from_session(
    session: _CompileSession, harness_name: HarnessName
) -> CompiledHarnessBundle:
    from cheese_flow.lib.emit import (
        emit_hooks,
        emit_mcp_config,
        emit_plugin_manifest,
    )

    adapter = HARNESS_ADAPTERS[harness_name]
    output_root = session.projectRoot / adapter.outputRoot
    agent_output = output_root / adapter.agentDirectory
    skill_output = output_root / adapter.skillDirectory

    await _clean_generated_artifacts(adapter, output_root)
    agent_output.mkdir(parents=True, exist_ok=True)
    skill_output.mkdir(parents=True, exist_ok=True)

    agents = await _compile_agents(
        project_root=session.projectRoot,
        harness=harness_name,
        agent_output_directory=agent_output,
        model_manifest=session.modelManifest,
    )
    skills = await _copy_skills(
        project_root=session.projectRoot,
        skill_output_directory=skill_output,
    )

    commands: list[str] = []
    if adapter.commandDirectory is not None:
        command_output = output_root / adapter.commandDirectory
        command_output.mkdir(parents=True, exist_ok=True)
        commands = await _copy_commands(
            project_root=session.projectRoot,
            command_output_directory=command_output,
        )

    if adapter.emitSurface is None:
        emitted_surface: SurfaceEmissionResult = {"rules": [], "commands": []}
    else:
        emitted_surface = await adapter.emitSurface(
            str(session.skillSourceDirectory), str(output_root)
        )

    component_paths = _build_manifest_component_paths(
        adapter=adapter,
        agents=agents,
        skills=skills,
        commands=commands,
        emitted_surface=emitted_surface,
    )

    _write_manifest(
        output_root,
        harness=harness_name,
        agents=agents,
        skills=skills,
        commands=commands,
    )

    emit_plugin_manifest(
        harness_name, session.pluginMetadata, output_root, component_paths
    )
    emit_mcp_config(harness_name, output_root)
    emit_hooks(harness_name, session.hooksSource, output_root)

    return CompiledHarnessBundle(
        harness=harness_name,
        outputRoot=str(output_root),
        pluginMetadata=session.pluginMetadata,
    )


def _write_manifest(
    output_root: Path,
    *,
    harness: HarnessName,
    agents: list[str],
    skills: list[str],
    commands: list[str],
) -> None:
    payload = {
        "harness": harness,
        "agents": agents,
        "skills": skills,
        "commands": commands,
        "generatedAt": datetime.now(tz=UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }
    (output_root / "manifest.json").write_text(_dump_json(payload), encoding="utf-8")


async def _compile_agents(
    *,
    project_root: Path,
    harness: HarnessName,
    agent_output_directory: Path,
    model_manifest: ModelManifest | None,
) -> list[str]:
    source_directory = project_root / "agents"
    entries = sorted(p.name for p in source_directory.iterdir())
    compiled: list[str] = []

    for entry_name in entries:
        source_path = source_directory / entry_name
        if not source_path.is_file() or not entry_name.endswith(".md.eta"):
            continue

        source = source_path.read_text(encoding="utf-8")
        data, body = parse_frontmatter(source)
        frontmatter = parse_agent_frontmatter(data)
        adapter = HARNESS_ADAPTERS[harness]
        output_file = f"{frontmatter.name}.md"
        base_model = resolve_model(frontmatter.models, harness)
        resolved_model = apply_model_manifest(
            model=base_model,
            agent_name=frontmatter.name,
            harness=harness,
            manifest=model_manifest,
        )
        agent_context = frontmatter.model_dump(by_alias=True, exclude_none=True)
        agent_context["model"] = resolved_model

        rendered = _render_template(
            body,
            agent=agent_context,
            harness=adapter,
        )

        final_content = _build_agent_file(
            frontmatter, adapter, resolved_model, rendered
        )
        (agent_output_directory / output_file).write_text(final_content, encoding="utf-8")
        compiled.append(output_file)

    return compiled


def _render_template(template_body: str, *, agent: dict[str, Any], harness: HarnessAdapter) -> str:
    jinja_src = _eta_to_jinja(template_body)
    template = _JINJA_ENV.from_string(jinja_src)
    return template.render(it={"agent": agent, "harness": harness})


async def _copy_skills(
    *, project_root: Path, skill_output_directory: Path
) -> list[str]:
    source_directory = project_root / "skills"
    entries = sorted(p.name for p in source_directory.iterdir())
    copied: list[str] = []

    for entry_name in entries:
        skill_directory = source_directory / entry_name
        if not skill_directory.is_dir():
            continue
        skill_md = skill_directory / "SKILL.md"
        data, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        frontmatter = parse_skill_frontmatter(data)

        if frontmatter.name != entry_name:
            raise ValueError(
                f'Skill directory "{entry_name}" must match frontmatter '
                f'name "{frontmatter.name}".'
            )

        destination = skill_output_directory / entry_name
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(skill_directory, destination)
        copied.append(entry_name)

    return copied


async def _copy_commands(
    *, project_root: Path, command_output_directory: Path
) -> list[str]:
    source_directory = project_root / "commands"
    if not source_directory.exists():
        return []
    entries = sorted(p.name for p in source_directory.iterdir())
    copied: list[str] = []

    for entry_name in entries:
        source_path = source_directory / entry_name
        if not source_path.is_file() or not entry_name.endswith(".md"):
            continue
        data, _ = parse_frontmatter(source_path.read_text(encoding="utf-8"))
        frontmatter = parse_command_frontmatter(data)
        base_name = entry_name[:-3]

        if frontmatter.name != base_name:
            raise ValueError(
                f'Command file "{entry_name}" must match frontmatter '
                f'name "{frontmatter.name}".'
            )

        shutil.copyfile(source_path, command_output_directory / entry_name)
        copied.append(entry_name)

    return copied


async def preview_agent(
    project_root: str | Path, agent_file: str, harness: HarnessName
) -> str:
    project_root = Path(project_root)
    source_path = project_root / "agents" / agent_file
    source = source_path.read_text(encoding="utf-8")
    data, body = parse_frontmatter(source)
    frontmatter = parse_agent_frontmatter(data)
    manifest = read_model_manifest(project_root)
    base_model = resolve_model(frontmatter.models, harness)
    resolved_model = apply_model_manifest(
        model=base_model,
        agent_name=frontmatter.name,
        harness=harness,
        manifest=manifest,
    )
    agent_context = frontmatter.model_dump(by_alias=True, exclude_none=True)
    agent_context["model"] = resolved_model
    rendered = _render_template(
        body, agent=agent_context, harness=HARNESS_ADAPTERS[harness]
    )
    return rendered.strip()


async def read_skill(project_root: str | Path, skill_name: str) -> SkillFrontmatter:
    source_path = Path(project_root) / "skills" / skill_name / "SKILL.md"
    source = source_path.read_text(encoding="utf-8")
    data, _ = parse_frontmatter(source)
    return parse_skill_frontmatter(data)
