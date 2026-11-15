"""Cross-system contract tests for the ff-consumer engine client.

Owner: ff-consumer. Contract register: ff-engine/docs/debugging-plan-2026-11-12.md §3.

Phase 0 skeleton: proves the fixture harness loads. Per-bug assertions are
added with each fix (C2/H2/H5, C3, C4, H1, H6).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

REQUIRED_FIXTURES = [
    "search_response.json",
    "dish_detail.json",
    "missing_response.json",
    "regions_response.json",
    "version_response.json",
    "submission_response.json",
]


@pytest.mark.parametrize("name", REQUIRED_FIXTURES)
def test_contract_fixture_loads(name: str) -> None:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data
