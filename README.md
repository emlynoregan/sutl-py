# sutl-py

`sutl-py` is the dependency-free Python implementation of **sUTL 1.0**, the
sUTL Universal Transform Language (“subtle”). sUTL programs are JSON-compatible
values that transform maps, lists, strings, numbers, booleans, and null.

The normative language specification and conformance corpus live in
[sutl-language](https://github.com/emlynoregan/sutl-language).

## Install

```console
python -m pip install sutl-py
```

Python 3.9 or later is required.

## Python API

```python
from sutl import Runner, compilelib, evaluate, truthy

result = evaluate(
    {"person": {"name": "Ada"}},
    {"name": "^$.person.name"},
)
assert result == {"name": "Ada"}
```

`evaluate(source, transform, library=None)` creates a runner for one
evaluation. Reuse `Runner().evaluate(...)` when making repeated calls.
`compilelib(...)` resolves declaration requirements into a transform library.
`truthy(value)` exposes sUTL truthiness.

The public API is typed and the distribution includes `py.typed`.

## Command line

The `sutl` command accepts JSON literals directly:

```console
sutl '{"value":4}' '["&+","^$.value",1]'
5
```

Prefix an argument with `@` to read JSON from a UTF-8 file. Use `-` as the
source to read it from standard input:

```console
sutl @source.json @transform.json --library @library.json --pretty
```

`python -m sutl` provides the same interface.

## Development

```console
python -m pip install -e ".[test,build]"
python -m pytest
python -m build
python -m twine check dist/*
```

The tests vendor the exact sUTL 1.0 contract, all 88 conformance cases, and all
44 Studio fixtures. They also verify the corpus SHA-256 checksum pinned by the
contract.

## License

Apache-2.0.
