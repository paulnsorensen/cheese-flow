"""Port of ``tests/compiler-commands.test.ts`` — covers ``compile_harness_bundles``
command output (manifest entries, copied content, mismatch errors).
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from cheese_flow.lib.compiler import compile_harness_bundles
from cheese_flow.lib.schemas import parse_command_frontmatter

REPO_ROOT = Path(__file__).resolve().parents[2]


def _seed_agents_and_skills(project_root: Path) -> None:
    shutil.copytree(REPO_ROOT / "agents", project_root / "agents")
    shutil.copytree(REPO_ROOT / "skills", project_root / "skills")


def _read_manifest(project_root: Path, output_root: str) -> dict:
    return json.loads((project_root / output_root / "manifest.json").read_text(encoding="utf-8"))


def test_copies_command_files_and_lists_them_in_manifest_for_both_harnesses(
    tmp_path: Path,
) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_agents_and_skills(project_root)
    commands = project_root / "commands"
    commands.mkdir()
    (commands / "alpha.md").write_text(
        "---\nname: alpha\n"
        "description: First portable command.\n"
        'argument-hint: "<input>"\n'
        "---\n# Alpha\n",
        encoding="utf-8",
    )
    (commands / "beta.md").write_text(
        "---\nname: beta\ndescription: Second portable command.\n---\n# Beta\n",
        encoding="utf-8",
    )
    (commands / "notes.txt").write_text("ignore me\n", encoding="utf-8")

    asyncio.run(
        compile_harness_bundles(
            project_root=project_root,
            harnesses=["claude-code", "codex"],
        )
    )

    for root in (".claude", ".codex"):
        manifest = _read_manifest(project_root, root)
        assert manifest["commands"] == ["alpha.md", "beta.md"]
        plugin_dir = ".claude-plugin" if root == ".claude" else ".codex-plugin"
        plugin_manifest = json.loads(
            (project_root / root / plugin_dir / "plugin.json").read_text(encoding="utf-8")
        )
        if root == ".claude":
            assert plugin_manifest["commands"] == "./commands/"
            assert "apps" not in plugin_manifest
        else:
            assert "commands" not in plugin_manifest
            assert plugin_manifest["apps"] == "./commands/"
        copied = (project_root / root / "commands" / "alpha.md").read_text(encoding="utf-8")
        assert "name: alpha" in copied
        assert "# Alpha" in copied


def test_propagates_non_enoent_readdir_errors_from_commands_directory(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_agents_and_skills(project_root)
    # commands path is a regular file, not a directory — readdir should fail.
    (project_root / "commands").write_text("this is a file, not a directory", encoding="utf-8")

    with pytest.raises(Exception):  # noqa: B017
        asyncio.run(
            compile_harness_bundles(
                project_root=project_root,
                harnesses=["claude-code"],
            )
        )


def test_rejects_commands_whose_filename_does_not_match_frontmatter_name(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_agents_and_skills(project_root)
    commands = project_root / "commands"
    commands.mkdir()
    (commands / "wrong-name.md").write_text(
        "---\nname: right-name\ndescription: Mismatched command file.\n---\n# Wrong\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="must match frontmatter name"):
        asyncio.run(
            compile_harness_bundles(
                project_root=project_root,
                harnesses=["claude-code"],
            )
        )


def test_validates_command_frontmatter_contract() -> None:
    command = parse_command_frontmatter(
        {
            "name": "cheese",
            "description": "Top-level router command.",
            "argument-hint": "<input>",
        }
    )
    assert command.name == "cheese"
    assert command.argument_hint == "<input>"


def test_copies_all_eight_scaffolded_top_level_commands_into_each_harness(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    _seed_agents_and_skills(project_root)
    shutil.copytree(REPO_ROOT / "commands", project_root / "commands")

    asyncio.run(
        compile_harness_bundles(
            project_root=project_root,
            harnesses=["claude-code", "codex"],
        )
    )

    expected = [
        "age.md",
        "briesearch.md",
        "cheese.md",
        "cook.md",
        "culture.md",
        "cure.md",
        "mold.md",
        "nih-audit.md",
    ]
    for root in (".claude", ".codex"):
        manifest = _read_manifest(project_root, root)
        assert sorted(manifest["commands"]) == expected
