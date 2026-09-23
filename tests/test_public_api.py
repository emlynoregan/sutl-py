"""Tests for package metadata and supported entry points."""

from __future__ import annotations

import json

import sutl
from sutl.cli import main


def test_public_exports() -> None:
    assert sutl.__version__ == "1.0.0"
    assert sutl.__all__ == [
        "Runner",
        "__version__",
        "compilelib",
        "evaluate",
        "truthy",
    ]
    assert sutl.Runner().evaluate({"x": 3}, "^$.x") == 3
    assert sutl.truthy([0])


def test_cli_json_literals(capsys: object) -> None:
    assert main(['{"value":4}', '["&+","^$.value",1]']) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out) == 5
