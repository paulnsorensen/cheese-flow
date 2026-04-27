"""Unit tests for the milknado planning slice (validation + stub planner)."""

from __future__ import annotations

import pytest
from milknado import FileChange, SymbolRef
from milknado.domains.planning import (
    dict_to_file_change,
    dict_to_new_relationship,
    plan_batches_stub,
    plan_to_dict,
)


def test_dict_to_file_change_roundtrip() -> None:
    fc = dict_to_file_change(
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
    # frozen tuple types
    assert isinstance(fc.symbols, tuple)
    assert isinstance(fc.depends_on, tuple)


def test_dict_to_file_change_rejects_traversal() -> None:
    with pytest.raises(ValueError, match="repo-relative"):
        dict_to_file_change({"id": "c1", "path": "../etc/passwd"})
    with pytest.raises(ValueError, match="repo-relative"):
        dict_to_file_change({"id": "c1", "path": "/abs/path.py"})
    with pytest.raises(ValueError, match="symbols"):
        dict_to_file_change(
            {
                "id": "c1",
                "path": "src/foo.py",
                "symbols": [{"name": 42, "file": "src/foo.py"}],
            }
        )


def test_dict_to_new_relationship_rejects_invalid_reason() -> None:
    with pytest.raises(ValueError, match="invalid reason"):
        dict_to_new_relationship(
            {"source_change_id": "a", "dependant_change_id": "b", "reason": "bogus"}
        )
    rel = dict_to_new_relationship(
        {"source_change_id": "a", "dependant_change_id": "b", "reason": "new_import"}
    )
    assert rel.reason == "new_import"
    assert rel.source_change_id == "a"
    assert rel.dependant_change_id == "b"


def test_plan_batches_stub_returns_single_batch() -> None:
    changes = [
        FileChange(id="a", path="src/a.py"),
        FileChange(id="b", path="src/b.py"),
    ]
    plan = plan_batches_stub(changes, budget=70_000)
    assert len(plan.batches) == 1
    assert plan.batches[0].change_ids == ("a", "b")
    assert plan.batches[0].depends_on == ()
    assert plan.batches[0].oversized is False
    assert plan.solver_status == "STUB"
    assert plan.spread_report == ()


def test_plan_to_dict_shape() -> None:
    changes = [
        FileChange(id="a", path="src/a.py"),
        FileChange(id="b", path="src/b.py"),
    ]
    plan = plan_batches_stub(changes, budget=70_000)
    serialized = plan_to_dict(plan)
    assert serialized == {
        "batches": [
            {
                "index": 0,
                "change_ids": ["a", "b"],
                "depends_on": [],
                "oversized": False,
            }
        ],
        "spread_report": [],
        "solver_status": "STUB",
    }
    # explicit list-not-tuple check on nested fields
    assert isinstance(serialized["batches"][0]["change_ids"], list)
    assert isinstance(serialized["batches"][0]["depends_on"], list)
