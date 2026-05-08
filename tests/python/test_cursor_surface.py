"""Port of ``tests/cursor-surface.test.ts`` — covers ``cursor_adapter.emit_surface``."""

from __future__ import annotations

import asyncio
from pathlib import Path

from cheese_flow.adapters.cursor import cursor_adapter


def _emit(skills_dir: Path, output_root: Path):  # type: ignore[no-untyped-def]
    assert cursor_adapter.emitSurface is not None, "cursor_adapter.emitSurface is None"
    return asyncio.run(cursor_adapter.emitSurface(str(skills_dir), str(output_root)))


def _write_skill(skills_dir: Path, name: str, content: str) -> Path:
    skill_dir = skills_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(content, encoding="utf-8")
    return skill_md


def test_emits_both_mdc_rule_and_md_command_for_a_skill(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir,
        "foo",
        "---\nname: foo\ndescription: A test skill\n---\n# Foo Skill\n\nThis is a test.\n",
    )
    output_root = tmp_path / "out"
    _emit(skills_dir, output_root)
    rule = (output_root / "rules" / "foo.mdc").read_text(encoding="utf-8")
    command = (output_root / "commands" / "foo.md").read_text(encoding="utf-8")
    assert "---" in rule
    assert "---" not in command


def test_mdc_rule_has_description_and_always_apply_frontmatter(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir,
        "test-skill",
        "---\nname: test-skill\ndescription: Test description\n---\n# Body\n",
    )
    output_root = tmp_path / "out"
    _emit(skills_dir, output_root)
    rule = (output_root / "rules" / "test-skill.mdc").read_text(encoding="utf-8")
    assert "description:" in rule
    assert "alwaysApply: false" in rule


def test_command_file_has_no_frontmatter(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir,
        "cmd-skill",
        "---\nname: cmd-skill\ndescription: Command test\n---\n# Body Content\n",
    )
    output_root = tmp_path / "out"
    _emit(skills_dir, output_root)
    command = (output_root / "commands" / "cmd-skill.md").read_text(encoding="utf-8")
    assert command.split("\n", 1)[0] != "---"


def test_both_rule_and_command_contain_body_content(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    body = "# Test Body\n\nSome content here."
    _write_skill(
        skills_dir,
        "content-skill",
        f"---\nname: content-skill\ndescription: Content test\n---\n{body}\n",
    )
    output_root = tmp_path / "out"
    _emit(skills_dir, output_root)
    rule = (output_root / "rules" / "content-skill.mdc").read_text(encoding="utf-8")
    command = (output_root / "commands" / "content-skill.md").read_text(encoding="utf-8")
    assert "# Test Body" in rule
    assert "# Test Body" in command


def test_emits_all_skills_when_multiple_exist(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(
        skills_dir,
        "skill-one",
        "---\nname: skill-one\ndescription: First skill\n---\n# One\n",
    )
    _write_skill(
        skills_dir,
        "skill-two",
        "---\nname: skill-two\ndescription: Second skill\n---\n# Two\n",
    )
    output_root = tmp_path / "out"
    _emit(skills_dir, output_root)
    rule1 = (output_root / "rules" / "skill-one.mdc").read_text(encoding="utf-8")
    rule2 = (output_root / "rules" / "skill-two.mdc").read_text(encoding="utf-8")
    cmd1 = (output_root / "commands" / "skill-one.md").read_text(encoding="utf-8")
    cmd2 = (output_root / "commands" / "skill-two.md").read_text(encoding="utf-8")
    assert "First skill" in rule1
    assert "Second skill" in rule2
    assert "# One" in cmd1
    assert "# Two" in cmd2


def test_returns_empty_result_when_skills_dir_does_not_exist(tmp_path: Path) -> None:
    output_root = tmp_path / "out"
    output_root.mkdir()
    result = _emit(Path("/does/not/exist"), output_root)
    assert result == {"rules": [], "commands": []}


def test_skips_subdirectory_without_skill_md(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    (skills_dir / "no-skill-md").mkdir(parents=True, exist_ok=True)
    output_root = tmp_path / "out"
    result = _emit(skills_dir, output_root)
    assert result == {"rules": [], "commands": []}


def test_skips_non_directory_entries_in_skills_dir(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "not-a-dir.md").write_text("# ignored\n", encoding="utf-8")
    output_root = tmp_path / "out"
    result = _emit(skills_dir, output_root)
    assert result == {"rules": [], "commands": []}


def test_uses_empty_description_when_skill_md_has_no_description_field(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    _write_skill(skills_dir, "no-desc", "---\nname: no-desc\n---\n# Body only\n")
    output_root = tmp_path / "out"
    _emit(skills_dir, output_root)
    rule = (output_root / "rules" / "no-desc.mdc").read_text(encoding="utf-8")
    assert "description: \n" in rule
    assert "# Body only" in rule
