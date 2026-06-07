"""Port of ``tests/cure-flow.test.ts`` — assertions on shipped /cure artifacts."""

from __future__ import annotations

import re
from pathlib import Path

from cheese_flow.lib.frontmatter import parse_frontmatter
from cheese_flow.lib.schemas import (
    parse_command_frontmatter,
    parse_skill_frontmatter,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


def test_ships_thin_cure_command_shim_pointing_at_skill() -> None:
    source = _read("commands/cure.md")
    data, body = parse_frontmatter(source)
    command = parse_command_frontmatter(data)
    assert command.name == "cure"
    assert re.search(r"cure|apply", command.description, re.IGNORECASE)
    assert re.search(r"load", body, re.IGNORECASE)
    assert re.search(r"user\s*gate|gate", body, re.IGNORECASE)
    assert re.search(r"apply", body, re.IGNORECASE)
    assert re.search(r"re-?age", body, re.IGNORECASE)
    assert "skills/cure/SKILL.md" in body


def test_command_disclaims_auto_execute_and_auto_chain() -> None:
    source = _read("commands/cure.md")
    _, body = parse_frontmatter(source)
    assert not re.search(r"\bauto-execute\b", body, re.IGNORECASE)
    assert not re.search(r"\bauto-chain\b", body, re.IGNORECASE)


def test_skill_md_has_cheese_flow_skill_frontmatter() -> None:
    source = _read("skills/cure/SKILL.md")
    data, _ = parse_frontmatter(source)
    frontmatter = parse_skill_frontmatter(data)
    assert frontmatter.name == "cure"
    assert frontmatter.metadata is not None
    assert frontmatter.metadata.get("owner") == "cheese-flow"


def test_skill_md_describes_ordered_loop_phases() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    ordered = re.compile(r"load[\s\S]*user\s*gate[\s\S]*apply[\s\S]*re-?age", re.IGNORECASE)
    assert ordered.search(body) is not None


def test_skill_md_enforces_user_gate_default_empty_no_auto() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert re.search(r"user\s*gate", body, re.IGNORECASE)
    assert re.search(
        r"default\s+(selection\s+)?(is\s+)?\*?\*?empty\*?\*?",
        body,
        re.IGNORECASE,
    )
    assert not re.search(r"\bauto-execute\b", body, re.IGNORECASE)
    assert not re.search(r"\bauto-chain\b", body, re.IGNORECASE)


def test_skill_md_references_public_skill_seams() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert "/cleanup" in body
    assert "/age" in body
    assert "/cook" in body


def test_skill_md_hardcodes_literal_cap_of_3_turns() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert re.search(
        r"\b3-turn\b|\bcap\s*=\s*3\b|\bturn\s*<\s*3\b|\b3\s*turns?\s+per\b",
        body,
        re.IGNORECASE,
    )
    assert not re.search(r"\bcap\s*=\s*[245]\b", body, re.IGNORECASE)
    assert not re.search(r"\bturn\s*<\s*[245]\b", body, re.IGNORECASE)
    assert not re.search(r"\b[245]-turn\b", body, re.IGNORECASE)


def test_skill_md_documents_user_gate_verbs_and_empty_default() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert re.search(r"\ball-high\b", body)
    assert re.search(r"\bnone\b", body)
    assert re.search(r"\bskip\s+\d|skip\s+N\b", body)
    assert re.search(
        r"default\s+(selection\s+)?(is\s+)?\*?\*?empty\*?\*?",
        body,
        re.IGNORECASE,
    )


def test_skill_md_loads_fixes_and_suggestions_and_merges() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert "fixes.json" in body
    assert "suggestions.json" in body
    assert re.search(r"merge|unified|merged", body, re.IGNORECASE)


def test_sources_md_documents_sidecar_paths_and_missing_sidecar_error() -> None:
    source = _read("skills/cure/references/sources.md")
    assert re.search(r"\.cheese/age/[^`\s]*\.fixes\.json", source)
    assert "suggestions.json" in source
    assert re.search(r"missing|error|not found", source, re.IGNORECASE)


def test_apply_router_md_maps_every_routing_type_to_its_handler() -> None:
    source = _read("skills/cure/references/apply-router.md")
    assert re.search(r"\bedit\b[\s\S]{0,80}/cleanup", source, re.IGNORECASE)
    assert re.search(
        r"\bsuggestion\b[\s\S]{0,120}cook[\s\S]{0,40}sub-?agent",
        source,
        re.IGNORECASE,
    )


def test_re_age_md_documents_3_turn_cap_age_scope_diff_semantics() -> None:
    source = _read("skills/cure/references/re-age.md")
    assert re.search(
        r"\b3-turn\b|\bcap\s*=\s*3\b|\bturn\s*<\s*3\b|\b3\s*turns?\b",
        source,
        re.IGNORECASE,
    )
    assert not re.search(r"\bcap\s*=\s*[245]\b", source, re.IGNORECASE)
    assert not re.search(r"\bturn\s*<\s*[245]\b", source, re.IGNORECASE)
    assert re.search(r"/age\s+--scope", source)
    assert "touched_paths" in source
    assert re.search(r"\bdiff\b[\s\S]{0,80}\bprior\b", source, re.IGNORECASE)
    assert re.search(r"\bnew\b\s+or\s+changed|only\s+new[/\s]", source, re.IGNORECASE)


def test_re_age_md_mentions_turn_log_path() -> None:
    source = _read("skills/cure/references/re-age.md")
    assert re.search(r"\.cheese/cure/[^`\s]*turns\.log\.json", source)


def test_command_argument_hint_pins_slug() -> None:
    source = _read("commands/cure.md")
    data, _ = parse_frontmatter(source)
    command = parse_command_frontmatter(data)
    assert command.argument_hint is not None
    assert "<slug>" in command.argument_hint


def test_skill_md_pins_comma_separated_specific_ids_verb() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert "1,3,5" in body


def test_skill_md_uses_literal_skip_n_placeholder() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert re.search(r"\bskip\s+N\b", body)


def test_skill_md_frames_cure_as_single_post_age_finisher() -> None:
    source = _read("skills/cure/SKILL.md")
    _, body = parse_frontmatter(source)
    assert re.search(
        r"\bsingle\b[^\n]{0,40}(hand-?off\s+target|finisher)",
        body,
        re.IGNORECASE,
    )


def test_re_age_md_captures_post_implementation_review_flag_for_cap() -> None:
    source = _read("skills/cure/references/re-age.md")
    assert re.search(r"post-?implementation\s+review", source, re.IGNORECASE)
    assert re.search(r"tune|tuning", source, re.IGNORECASE)


def test_apply_router_md_names_agent_brief_for_cook_payload() -> None:
    source = _read("skills/cure/references/apply-router.md")
    assert "agent_brief_for_cook" in source
