"""Tests for the milknado planning slice via the external package."""

from __future__ import annotations

import pytest
from cheese_flow.mcp_server import (
    _dict_to_file_change,
    _dict_to_new_relationship,
    _plan_to_dict,
)
from milknado.domains.batching import FileChange, SymbolRef, plan_batches


def test_dict_to_file_change_roundtrip() -> None:
    fc = _dict_to_file_change(
        {
            "id": "c1",
            "path": "src/foo.py",
            "edit_kind": "modify",
            "symbols": [{"name": "foo", "file": "src/foo.py"}],
            "depends_on": ["c0"],
        }
    )
    assert fc == FileChange(
        id="c1",
        path="src/foo.py",
        edit_kind="modify",
        symbols=(SymbolRef(name="foo", file="src/foo.py"),),
        depends_on=("c0",),
    )
    assert isinstance(fc.symbols, tuple)
    assert isinstance(fc.depends_on, tuple)


def test_dict_to_file_change_rejects_missing_id() -> None:
    with pytest.raises(ValueError, match="id"):
        _dict_to_file_change({"path": "src/foo.py"})


def test_dict_to_file_change_rejects_missing_path() -> None:
    with pytest.raises(ValueError, match="path"):
        _dict_to_file_change({"id": "c1", "path": ""})


def test_dict_to_file_change_rejects_symbol_missing_file() -> None:
    # Agent-supplied MCP input must fail loud with a clear ValueError,
    # not a bare KeyError, when a symbol omits its file.
    with pytest.raises(ValueError, match="file"):
        _dict_to_file_change({"id": "c1", "path": "src/foo.py", "symbols": [{"name": "foo"}]})


def test_dict_to_new_relationship_rejects_missing_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        _dict_to_new_relationship({"source_change_id": "a", "dependant_change_id": "b"})


def test_dict_to_new_relationship_rejects_invalid_reason() -> None:
    with pytest.raises(ValueError, match="invalid reason"):
        _dict_to_new_relationship(
            {"source_change_id": "a", "dependant_change_id": "b", "reason": "bogus"}
        )
    rel = _dict_to_new_relationship(
        {"source_change_id": "a", "dependant_change_id": "b", "reason": "new_import"}
    )
    assert rel.reason == "new_import"
    assert rel.source_change_id == "a"
    assert rel.dependant_change_id == "b"


def test_plan_batches_returns_valid_status() -> None:
    changes = [
        FileChange(id="a", path="src/a.py"),
        FileChange(id="b", path="src/b.py"),
    ]
    plan = plan_batches(changes, 70_000)
    assert plan.solver_status in {"OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN"}
    # both changes must appear somewhere in the batches
    all_ids = {cid for b in plan.batches for cid in b.change_ids}
    assert all_ids == {"a", "b"}


def test_plan_to_dict_shape() -> None:
    changes = [
        FileChange(id="a", path="src/a.py"),
        FileChange(id="b", path="src/b.py"),
    ]
    plan = plan_batches(changes, 70_000)
    serialized = _plan_to_dict(plan)
    assert "solver_status" in serialized
    assert "batches" in serialized
    assert "spread_report" in serialized
    # all change ids present across batches
    all_ids = {cid for b in serialized["batches"] for cid in b["change_ids"]}
    assert all_ids == {"a", "b"}
    # list types, not tuple
    for b in serialized["batches"]:
        assert isinstance(b["change_ids"], list)
        assert isinstance(b["depends_on"], list)
