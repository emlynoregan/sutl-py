"""Run the complete vendored sUTL 1.0 contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from sutl import compilelib, evaluate


CONTRACT_ROOT = Path(__file__).parent / "contract"
CONTRACT = json.loads(
    (CONTRACT_ROOT / "contract.json").read_text(encoding="utf-8")
)
CORPUS_PATH = CONTRACT_ROOT / "conformance.json"
CORPUS = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))


def same(left: Any, right: Any) -> bool:
    """Compare MLSNBN values while keeping booleans distinct from numbers."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            same(left[key], right[key]) for key in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            same(a, b) for a, b in zip(left, right)
        )
    return left == right


def bundle_library(bundle: dict[str, Any]) -> dict[str, Any]:
    declarations = bundle.get("library") or []
    library = {
        declaration["name"]: declaration["transform-t"]
        for declaration in declarations
        if isinstance(declaration, dict)
        and "name" in declaration
        and "transform-t" in declaration
    }
    for required in (bundle.get("declaration") or {}).get("requires", []):
        match = next(
            (
                declaration
                for declaration in declarations
                if declaration.get("name", "").startswith(required)
            ),
            None,
        )
        if match:
            library[required] = match["transform-t"]
    return library


def run_case(case: dict[str, Any]) -> Any:
    source = case.get("source")
    library = dict(case.get("library", {}))
    mode = case.get("mode", "evaluate")
    if mode == "evaluate":
        return evaluate(source, case["transform"], library)
    if mode == "compilelib_evaluate":
        compiled = compilelib(
            [case["declaration"]],
            case.get("distributions", []),
            seed=library,
            test=case.get("test", False),
        )
        if "fail" in compiled:
            return {"compile-fail": compiled["fail"]}
        return evaluate(
            source,
            case["declaration"]["transform-t"],
            compiled["lib"],
        )
    if mode == "declaration_test_t":
        return "fail" not in compilelib(
            [case["declaration"]],
            case.get("distributions", []),
            seed=library,
            test=True,
        )
    if mode == "studio_fixture_set":
        failures = []
        paths = sorted(CONTRACT_ROOT.glob(case["fixture_glob"]))
        for path in paths:
            fixture = json.loads(path.read_text(encoding="utf-8"))
            try:
                actual = evaluate(
                    fixture.get("source"),
                    fixture.get("transform"),
                    bundle_library(fixture),
                )
                if not same(actual, fixture.get("expected")):
                    failures.append(fixture["id"])
            except Exception as error:  # pragma: no cover - shown on failure
                failures.append(f"{fixture['id']}: {error}")
        return {"evaluated": len(paths), "failures": failures}
    raise ValueError(f"unknown conformance mode: {mode}")


def test_contract_and_corpus_checksum() -> None:
    assert CONTRACT == {
        "language": "sUTL",
        "version": "1.0.0",
        "conformance_format": "sutl-conformance-1.0",
        "corpus_sha256": (
            "18be3a8143a7a1aa2d1d25b4167de67475478952ffe622b3369b0d72802e25e4"
        ),
    }
    assert hashlib.sha256(CORPUS_PATH.read_bytes()).hexdigest() == CONTRACT[
        "corpus_sha256"
    ]
    assert CORPUS["format"] == CONTRACT["conformance_format"]
    assert CORPUS["dialect"] == CONTRACT["language"]
    assert len(CORPUS["cases"]) == 88


@pytest.mark.parametrize(
    "case",
    CORPUS["cases"],
    ids=[case["id"] for case in CORPUS["cases"]],
)
def test_conformance_case(case: dict[str, Any]) -> None:
    assert same(run_case(case), case["expected"])
