"""Runtime limits stop evaluation without changing results inside the budget."""

import sutl


def loop():
    return {"!": "^$.loop", "loop": {"!": "^$.loop"}}


def test_steps_and_depth():
    assert sutl.evaluate(None, 1, limits=sutl.Limits(max_steps=1)) == 1
    try:
        sutl.evaluate(None, {"a": 1}, limits=sutl.Limits(max_steps=1))
    except sutl.LimitError as error:
        assert error.reason == "steps"
    else:
        raise AssertionError("expected a step limit")
    try:
        sutl.evaluate(None, {"a": 1}, limits=sutl.Limits(max_depth=1))
    except sutl.LimitError as error:
        assert error.reason == "depth"
    else:
        raise AssertionError("expected a depth limit")
    assert sutl.evaluate(None, {"a": 1}, limits=sutl.Limits(max_steps=2, max_depth=2)) == {"a": 1}


def test_cancel_and_compile():
    try:
        sutl.evaluate(None, 1, cancel=lambda: True)
    except sutl.LimitError as error:
        assert error.reason == "cancelled"
    else:
        raise AssertionError("expected cancellation")

    source = loop()
    try:
        sutl.evaluate(source, source, limits=sutl.Limits(max_depth=8))
    except sutl.LimitError as error:
        assert error.reason == "depth"
    else:
        raise AssertionError("expected the loop to hit the depth limit")

    program = sutl.compile_limited("^$.name", limits=sutl.Limits(max_steps=100_000, max_depth=256))
    assert program.run({"name": "Ada"}) == "Ada"


def test_negative_limits():
    try:
        sutl.Limits(max_steps=-1)
    except ValueError:
        return
    raise AssertionError("expected negative limits to be rejected")
