"""Dependency-free evaluator for the sUTL 1.0 language contract."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable


MLSNBN = Any
Builtin = Callable[[MLSNBN, dict[str, MLSNBN], dict[str, MLSNBN], MLSNBN, MLSNBN], MLSNBN]


def is_map(value: MLSNBN) -> bool:
    return isinstance(value, dict)


def is_list(value: MLSNBN) -> bool:
    return isinstance(value, list)


def is_string(value: MLSNBN) -> bool:
    return isinstance(value, str)


def is_number(value: MLSNBN) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def truthy(value: MLSNBN) -> bool:
    return bool(value)


def _path_step(values: MLSNBN, selector: MLSNBN) -> list[MLSNBN]:
    result: list[MLSNBN] = []
    if not is_list(values):
        return result
    if selector is None or selector == "":
        return values

    for value in values:
        try:
            if selector == "**":
                result.append(value)
                stack = [value]
                while stack:
                    current = stack.pop()
                    if is_map(current):
                        children = list(current.values())
                        result.extend(children)
                        stack.extend(children)
                    elif is_list(current):
                        result.extend(current)
                        stack.extend(current)
            elif selector == "*":
                if is_map(value):
                    result.extend(value.values())
                elif is_list(value):
                    result.extend(value)
            elif is_map(value) and is_string(selector) and selector in value:
                result.append(value[selector])
            elif is_list(value) and is_number(selector):
                index = int(selector)
                if index == selector and 0 <= index < len(value):
                    result.append(value[index])
        except (KeyError, TypeError, ValueError):
            pass
    return result


class LimitError(Exception):
    """Raised when evaluation exceeds a host limit or is cancelled."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"sUTL evaluation stopped: {reason}")


class Limits:
    """Bounds for one evaluation. Zero means that bound is unset."""

    def __init__(self, max_steps: int = 0, max_depth: int = 0) -> None:
        if max_steps < 0 or max_depth < 0:
            raise ValueError("limits must be >= 0")
        self.max_steps = max_steps
        self.max_depth = max_depth


class _Budget:
    def __init__(self, limits: Limits | None, cancel: Callable[[], bool] | None) -> None:
        self.steps = 0
        self.depth = 0
        self.max_steps = 0 if limits is None else limits.max_steps
        self.max_depth = 0 if limits is None else limits.max_depth
        self.cancel = cancel


class Program:
    """A transform plus the limits applied each time it runs."""

    def __init__(self, transform: MLSNBN, library: dict[str, MLSNBN] | None, limits: Limits) -> None:
        self.transform = transform
        self.library = library
        self.limits = limits

    def run(self, source: MLSNBN, *, cancel: Callable[[], bool] | None = None) -> MLSNBN:
        return evaluate(source, self.transform, self.library, limits=self.limits, cancel=cancel)


class Runner:
    """Evaluate sUTL transforms with an optional transform library."""

    def __init__(self) -> None:
        self.builtins: dict[str, Builtin] = self._make_builtins()
        self._budget: _Budget | None = None

    def evaluate(
        self,
        source: MLSNBN,
        transform: MLSNBN,
        library: dict[str, MLSNBN] | None = None,
        *,
        limits: Limits | None = None,
        cancel: Callable[[], bool] | None = None,
    ) -> MLSNBN:
        active = cancel is not None or (
            limits is not None and (limits.max_steps > 0 or limits.max_depth > 0)
        )
        previous = self._budget
        self._budget = _Budget(limits, cancel) if active else None
        try:
            return self._evaluate(source, transform, library or {}, source, transform)
        finally:
            self._budget = previous

    def _charge(self) -> bool:
        budget = self._budget
        if budget is None:
            return False
        budget.steps += 1
        if budget.max_steps and budget.steps > budget.max_steps:
            raise LimitError("steps")
        if budget.cancel is not None and budget.cancel():
            raise LimitError("cancelled")
        if budget.max_depth and budget.depth >= budget.max_depth:
            raise LimitError("depth")
        budget.depth += 1
        return True

    def _release(self) -> None:
        if self._budget is not None:
            self._budget.depth -= 1

    def _evaluate(
        self,
        scope: MLSNBN,
        transform: MLSNBN,
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        charged = self._charge()
        try:
            return self._evaluate_unmetered(scope, transform, library, source, root_transform)
        finally:
            if charged:
                self._release()

    def _evaluate_unmetered(
        self,
        scope: MLSNBN,
        transform: MLSNBN,
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        if is_map(transform) and "!" in transform:
            return self._evaluate_eval(
                scope, transform, library, source, root_transform
            )
        if is_map(transform) and "!!" in transform:
            return self._evaluate_eval2(
                scope, transform, library, source, root_transform
            )
        if is_map(transform) and "&" in transform:
            return self._evaluate_builtin(
                scope, transform, library, source, root_transform
            )
        if is_map(transform) and "'" in transform:
            return self._quote(
                scope, transform["'"], library, source, root_transform
            )
        if is_map(transform) and ":" in transform:
            return transform[":"]
        if is_map(transform):
            return self._evaluate_map(
                scope, transform, library, source, root_transform
            )
        if self._is_compact_builtin(transform):
            return self._evaluate_compact(
                scope, transform, library, source, root_transform
            )
        if is_list(transform):
            values = transform[1:] if transform[:1] == ["&&"] else transform
            result = [
                self._evaluate(scope, item, library, source, root_transform)
                for item in values
            ]
            return self._flatten(result) if transform[:1] == ["&&"] else result
        return transform

    def _quote(
        self,
        scope: MLSNBN,
        transform: MLSNBN,
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        charged = self._charge()
        try:
            return self._quote_unmetered(scope, transform, library, source, root_transform)
        finally:
            if charged:
                self._release()

    def _quote_unmetered(
        self,
        scope: MLSNBN,
        transform: MLSNBN,
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        if is_map(transform) and "''" in transform:
            return self._evaluate(
                scope, transform["''"], library, source, root_transform
            )
        if is_map(transform):
            return {
                str(key): self._quote(
                    scope, value, library, source, root_transform
                )
                for key, value in transform.items()
            }
        if is_list(transform):
            return [
                self._quote(scope, value, library, source, root_transform)
                for value in transform
            ]
        return transform

    def _evaluate_map(
        self,
        scope: MLSNBN,
        transform: dict[str, MLSNBN],
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> dict[str, MLSNBN]:
        return {
            str(key): self._evaluate(
                scope, value, library, source, root_transform
            )
            for key, value in transform.items()
            if key not in ("!", "&")
        }

    def _evaluate_eval(
        self,
        scope: MLSNBN,
        transform: dict[str, MLSNBN],
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        next_transform = self._evaluate(
            scope, transform["!"], library, source, root_transform
        )
        next_scope = dict(scope) if is_map(scope) else {}
        next_scope.update(
            self._evaluate_map(
                scope, transform, library, source, root_transform
            )
        )
        next_library = (
            self._evaluate_map(
                scope, transform["*"], library, source, root_transform
            )
            if is_map(transform.get("*"))
            else library
        )
        return self._evaluate(
            next_scope, next_transform, next_library, source, root_transform
        )

    def _evaluate_eval2(
        self,
        scope: MLSNBN,
        transform: dict[str, MLSNBN],
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        next_transform = self._evaluate(
            scope, transform["!!"], library, source, root_transform
        )
        next_scope = scope
        if "s" in transform:
            scope_delta = self._evaluate(
                scope, transform["s"], library, source, root_transform
            )
            if is_map(scope_delta):
                next_scope = dict(scope) if is_map(scope) else {}
                next_scope.update(scope_delta)
            else:
                next_scope = scope_delta
        next_library = (
            self._evaluate_map(
                scope, transform["*"], library, source, root_transform
            )
            if is_map(transform.get("*"))
            else library
        )
        return self._evaluate(
            next_scope, next_transform, next_library, source, root_transform
        )

    def _is_compact_builtin(self, transform: MLSNBN) -> bool:
        if is_string(transform):
            parts: list[MLSNBN] = transform.split(".")
        elif is_list(transform):
            parts = transform
        else:
            return False
        if not parts or not is_string(parts[0]) or not parts[0]:
            return False
        operation = parts[0]
        return (
            operation[0] in ("&", "^")
            and operation[1:] in self.builtins
        )

    def _evaluate_compact(
        self,
        scope: MLSNBN,
        transform: str | list[MLSNBN],
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        parts: list[MLSNBN] = (
            transform.split(".") if is_string(transform) else list(transform)
        )
        if is_string(transform):
            converted: list[MLSNBN] = []
            for part in parts:
                try:
                    converted.append(int(part))
                except (TypeError, ValueError):
                    converted.append(part)
            parts = converted
        operation = parts[0]
        return self._evaluate_builtin(
            scope,
            {
                "&": operation[1:],
                "args": parts[1:],
                "head": operation[0] == "^",
            },
            library,
            source,
            root_transform,
        )

    def _evaluate_builtin(
        self,
        scope: MLSNBN,
        transform: dict[str, MLSNBN],
        library: dict[str, MLSNBN],
        source: MLSNBN,
        root_transform: MLSNBN,
    ) -> MLSNBN:
        arguments = transform.get("args")
        if is_list(arguments):
            if not arguments:
                result = self._evaluate_builtin(
                    scope,
                    {"&": transform.get("&")},
                    library,
                    source,
                    root_transform,
                )
            elif len(arguments) == 1:
                result = self._evaluate_builtin(
                    scope,
                    {
                        "&": transform.get("&"),
                        "b": self._evaluate(
                            scope, arguments[0], library, source, root_transform
                        ),
                    },
                    library,
                    source,
                    root_transform,
                )
            else:
                result = self._evaluate(
                    scope, arguments[0], library, source, root_transform
                )
                for index, item in enumerate(arguments[1:]):
                    result = self._evaluate_builtin(
                        scope,
                        {
                            "&": transform.get("&"),
                            "a": result,
                            "b": self._evaluate(
                                scope, item, library, source, root_transform
                            ),
                            "notfirst": index > 0,
                        },
                        library,
                        source,
                        root_transform,
                    )
            if transform.get("head"):
                return result[0] if is_list(result) and result else None
            return result

        name = transform.get("&")
        builtin = self.builtins.get(name)
        library_name = f"_override_{name}" if builtin else name
        if library_name in library:
            call = dict(transform)
            call["!"] = ["^*", library_name]
            del call["&"]
            return self._evaluate_eval(
                scope, call, library, source, root_transform
            )
        if not builtin:
            return None

        next_scope = dict(scope) if is_map(scope) else {}
        next_scope.update(
            self._evaluate_map(
                scope, transform, library, source, root_transform
            )
        )
        next_library = (
            self._evaluate_map(
                scope, transform["*"], library, source, root_transform
            )
            if is_map(transform.get("*"))
            else library
        )
        return builtin(scope, next_scope, next_library, source, root_transform)

    @staticmethod
    def _flatten(values: list[MLSNBN]) -> list[MLSNBN]:
        result: list[MLSNBN] = []
        for value in values:
            result.extend(value if is_list(value) else [value])
        return result

    def _make_builtins(self) -> dict[str, Builtin]:
        def binary(
            left: Callable[[dict[str, MLSNBN]], MLSNBN],
            right: Callable[[dict[str, MLSNBN]], MLSNBN],
            operation: Callable[[MLSNBN, MLSNBN], MLSNBN],
        ) -> Builtin:
            def run(
                parent: MLSNBN,
                scope: dict[str, MLSNBN],
                library: dict[str, MLSNBN],
                source: MLSNBN,
                root: MLSNBN,
            ) -> MLSNBN:
                try:
                    return operation(left(scope), right(scope))
                except (ArithmeticError, TypeError, ValueError):
                    return None

            return run

        def unary(
            value: Callable[[dict[str, MLSNBN]], MLSNBN],
            operation: Callable[[MLSNBN], MLSNBN],
        ) -> Builtin:
            def run(
                parent: MLSNBN,
                scope: dict[str, MLSNBN],
                library: dict[str, MLSNBN],
                source: MLSNBN,
                root: MLSNBN,
            ) -> MLSNBN:
                try:
                    return operation(value(scope))
                except (ArithmeticError, TypeError, ValueError):
                    return None

            return run

        def get(scope: dict[str, MLSNBN], key: str, default: MLSNBN) -> MLSNBN:
            value = scope.get(key)
            return default if value is None else value

        def equal(left: MLSNBN, right: MLSNBN) -> bool:
            compatible = (
                type(left) is type(right)
                or (is_number(left) and is_number(right))
                or (is_string(left) and is_string(right))
            )
            return compatible and left == right

        def add(left: MLSNBN, right: MLSNBN) -> MLSNBN:
            if (is_number(left) and is_number(right)) or (
                is_string(left) and is_string(right)
            ):
                return left + right
            raise TypeError("addition requires two numbers or two strings")

        def numeric(
            left: MLSNBN, right: MLSNBN, operation: Callable[[MLSNBN, MLSNBN], MLSNBN]
        ) -> MLSNBN:
            if not is_number(left) or not is_number(right):
                raise TypeError("numeric operation requires two numbers")
            return operation(left, right)

        def compare(
            left: MLSNBN, right: MLSNBN, operation: Callable[[MLSNBN, MLSNBN], bool]
        ) -> bool:
            return (
                is_number(left)
                and is_number(right)
                and operation(left, right)
            )

        def if_builtin(
            parent: MLSNBN,
            scope: dict[str, MLSNBN],
            library: dict[str, MLSNBN],
            source: MLSNBN,
            root: MLSNBN,
        ) -> MLSNBN:
            branch = "true" if truthy(scope.get("cond")) else "false"
            if branch not in scope:
                return None
            return self._evaluate(parent, scope[branch], library, source, root)

        def reduce_builtin(
            parent: MLSNBN,
            scope: dict[str, MLSNBN],
            library: dict[str, MLSNBN],
            source: MLSNBN,
            root: MLSNBN,
        ) -> MLSNBN:
            accumulator = scope.get("accum")
            values = scope.get("list")
            if is_list(values):
                for index, item in enumerate(values):
                    item_scope = dict(parent) if is_map(parent) else {}
                    item_scope.update(scope)
                    item_scope.update(
                        {"item": item, "accum": accumulator, "ix": index}
                    )
                    accumulator = self._evaluate(
                        item_scope, scope.get("t"), library, source, root
                    )
            return accumulator

        def path(start: MLSNBN) -> Builtin:
            def run(
                parent: MLSNBN,
                scope: dict[str, MLSNBN],
                library: dict[str, MLSNBN],
                source: MLSNBN,
                root: MLSNBN,
            ) -> list[MLSNBN]:
                left = scope.get("a")
                right = scope.get("b")
                if scope.get("notfirst"):
                    return _path_step(left, right)
                return _path_step(_path_step([start], left), right)

            return run

        def raw_path(
            parent: MLSNBN,
            scope: dict[str, MLSNBN],
            library: dict[str, MLSNBN],
            source: MLSNBN,
            root: MLSNBN,
        ) -> list[MLSNBN]:
            left = scope.get("a")
            right = scope.get("b")
            if scope.get("notfirst"):
                return _path_step(left, right)
            return _path_step([right], None) if left is None else _path_step([left], right)

        def string_value(value: MLSNBN) -> str:
            if is_string(value):
                return value
            if is_number(value):
                return str(value)
            if isinstance(value, bool):
                return "true" if value else "false"
            if value is None:
                return "null"
            if is_map(value):
                return "map"
            if is_list(value):
                return "list"
            return "unknown"

        def number_value(value: MLSNBN) -> MLSNBN:
            if is_number(value):
                return value
            if is_string(value):
                try:
                    return int(value)
                except ValueError:
                    try:
                        return float(value)
                    except ValueError:
                        return 0
            if isinstance(value, bool):
                return 1 if value else 0
            return 0

        def type_value(value: MLSNBN) -> str:
            if is_map(value):
                return "map"
            if is_list(value):
                return "list"
            if is_string(value):
                return "string"
            if is_number(value):
                return "number"
            if isinstance(value, bool):
                return "boolean"
            if value is None:
                return "null"
            return "unknown"

        builtins: dict[str, Builtin] = {
            "+": binary(
                lambda s: get(s, "a", 0),
                lambda s: get(s, "b", 0),
                add,
            ),
            "-": binary(
                lambda s: get(s, "a", 0),
                lambda s: get(s, "b", 0),
                lambda a, b: numeric(a, b, lambda x, y: x - y),
            ),
            "x": binary(
                lambda s: get(s, "a", 1),
                lambda s: get(s, "b", 1),
                lambda a, b: numeric(a, b, lambda x, y: x * y),
            ),
            "/": binary(
                lambda s: get(s, "a", 1),
                lambda s: get(s, "b", 1),
                lambda a, b: numeric(a, b, lambda x, y: x / y),
            ),
            "=": binary(
                lambda s: get(s, "a", None),
                lambda s: get(s, "b", None),
                equal,
            ),
            "!=": binary(
                lambda s: get(s, "a", None),
                lambda s: get(s, "b", None),
                lambda a, b: not equal(a, b),
            ),
            ">": binary(
                lambda s: s.get("a"),
                lambda s: s.get("b"),
                lambda a, b: compare(a, b, lambda x, y: x > y),
            ),
            "<": binary(
                lambda s: s.get("a"),
                lambda s: s.get("b"),
                lambda a, b: compare(a, b, lambda x, y: x < y),
            ),
            ">=": binary(
                lambda s: s.get("a"),
                lambda s: s.get("b"),
                lambda a, b: compare(a, b, lambda x, y: x >= y),
            ),
            "<=": binary(
                lambda s: s.get("a"),
                lambda s: s.get("b"),
                lambda a, b: compare(a, b, lambda x, y: x <= y),
            ),
            "&&": binary(
                lambda s: get(s, "a", False),
                lambda s: get(s, "b", False),
                lambda a, b: truthy(a) and truthy(b),
            ),
            "||": binary(
                lambda s: get(s, "a", False),
                lambda s: get(s, "b", False),
                lambda a, b: truthy(a) or truthy(b),
            ),
            "!": unary(lambda s: get(s, "b", False), lambda value: not truthy(value)),
            "if": if_builtin,
            "reduce": reduce_builtin,
            "$": path(None),
            "@": path(None),
            "^": path(None),
            "*": path(None),
            "~": path(None),
            "%": raw_path,
        }

        # Path starts depend on call context, unlike ordinary builtins.
        builtins["$"] = lambda p, s, l, src, root: self._process_path(src, s)
        builtins["@"] = lambda p, s, l, src, root: self._process_path(p, s)
        builtins["^"] = lambda p, s, l, src, root: self._process_path(s, s)
        builtins["*"] = lambda p, s, l, src, root: self._process_path(l, s)
        builtins["~"] = lambda p, s, l, src, root: self._process_path(root, s)

        builtins.update(
            {
                "zip": lambda p, s, l, src, root: deepcopy(
                    [list(items) for items in zip(*(s.get("list") or []))]
                ),
                "removekeys": lambda p, s, l, src, root: self._remove_keys(
                    s.get("map"), s.get("keys")
                ),
                "len": lambda p, s, l, src, root: (
                    len(s.get("list")) if is_list(s.get("list")) else 0
                ),
                "keys": lambda p, s, l, src, root: (
                    sorted(str(key) for key in s["map"])
                    if is_map(s.get("map"))
                    else None
                ),
                "values": lambda p, s, l, src, root: (
                    [s["map"][key] for key in sorted(s["map"])]
                    if is_map(s.get("map"))
                    else None
                ),
                "type": lambda p, s, l, src, root: type_value(s.get("value")),
                "makemap": lambda p, s, l, src, root: self._make_map(s.get("value")),
                "quicksort": lambda p, s, l, src, root: (
                    sorted(s.get("list")) if s.get("list") else s.get("list")
                ),
                "head": lambda p, s, l, src, root: (
                    s["b"][0] if is_list(s.get("b")) and s["b"] else None
                ),
                "tail": lambda p, s, l, src, root: (
                    s["b"][1:] if is_list(s.get("b")) else None
                ),
                "split": lambda p, s, l, src, root: self._split(
                    s.get("value"), s.get("sep"), s.get("max")
                ),
                "trim": lambda p, s, l, src, root: (
                    string_value(s.get("value")).strip() if s.get("value") else None
                ),
                "pos": lambda p, s, l, src, root: self._position(
                    s.get("value"), s.get("sub")
                ),
                "string": lambda p, s, l, src, root: string_value(s.get("value")),
                "number": lambda p, s, l, src, root: number_value(s.get("value")),
                "boolean": lambda p, s, l, src, root: truthy(s.get("value")),
                "lower": lambda p, s, l, src, root: string_value(s.get("value")).lower(),
                "upper": lambda p, s, l, src, root: string_value(s.get("value")).upper(),
            }
        )
        for name in list(builtins):
            builtins[f"has{name}"] = lambda p, s, l, src, root: True
        return builtins

    @staticmethod
    def _process_path(start: MLSNBN, scope: dict[str, MLSNBN]) -> list[MLSNBN]:
        left = scope.get("a")
        right = scope.get("b")
        if scope.get("notfirst"):
            return _path_step(left, right)
        return _path_step(_path_step([start], left), right)

    @staticmethod
    def _remove_keys(mapping: MLSNBN, keys: MLSNBN) -> MLSNBN:
        if mapping is None:
            return None
        result = deepcopy(mapping)
        for key in keys or []:
            result.pop(key, None)
        return result

    @staticmethod
    def _make_map(value: MLSNBN) -> MLSNBN:
        if not is_list(value):
            return None
        return {
            item[0]: item[1]
            for item in value
            if is_list(item) and len(item) >= 2 and is_string(item[0])
        }

    @staticmethod
    def _split(value: MLSNBN, separator: MLSNBN, maximum: MLSNBN) -> MLSNBN:
        if not value or (maximum and not is_number(maximum)):
            return None
        separator = separator or ","
        return str(value).split(str(separator), int(maximum)) if maximum else str(value).split(str(separator))

    @staticmethod
    def _position(value: MLSNBN, substring: MLSNBN) -> MLSNBN:
        if not value or not substring:
            return None
        return str(value).find(str(substring))


def evaluate(
    source: MLSNBN,
    transform: MLSNBN,
    library: dict[str, MLSNBN] | None = None,
    *,
    limits: Limits | None = None,
    cancel: Callable[[], bool] | None = None,
) -> MLSNBN:
    return Runner().evaluate(source, transform, library, limits=limits, cancel=cancel)


def compile_limited(
    transform: MLSNBN,
    library: dict[str, MLSNBN] | None = None,
    limits: Limits | None = None,
) -> Program:
    """Prepare a transform that runs under limits."""
    return Program(transform, library, limits or Limits())


def compilelib(
    declarations: list[dict[str, MLSNBN]],
    distributions: list[list[dict[str, MLSNBN]]],
    seed: dict[str, MLSNBN] | None = None,
    test: bool = False,
) -> dict[str, MLSNBN]:
    """Compile required declaration transforms into a library."""
    runner = Runner()
    result = dict(seed or {})
    failures: list[MLSNBN] = []

    def add_requirements(items: list[dict[str, MLSNBN]]) -> None:
        for declaration in items:
            declared_name = declaration.get("name", "")
            for required in declaration.get("requires", []):
                if required in result:
                    continue
                if declared_name.startswith(required):
                    result[required] = declaration.get("transform-t")
                    continue
                candidates = [
                    candidate
                    for distribution in distributions
                    for candidate in distribution
                    if candidate.get("name", "").startswith(required)
                ]
                if not candidates:
                    failures.append(f"missing requirement: {required}")
                    continue
                candidate_failures: list[MLSNBN] = []
                for candidate in candidates:
                    before = dict(result)
                    add_requirements([candidate])
                    if test and "test-t" in candidate:
                        candidate_library = {
                            name: result[name]
                            for name in candidate.get("requires", [])
                            if name in result
                        }
                        failure = runner.evaluate(
                            candidate.get("transform-t"),
                            candidate.get("test-t"),
                            candidate_library,
                        )
                        if truthy(failure):
                            candidate_failures.append(failure)
                            result.clear()
                            result.update(before)
                            continue
                    result[required] = candidate.get("transform-t")
                    candidate_failures = []
                    break
                failures.extend(candidate_failures)

    add_requirements(declarations)
    if test:
        for declaration in declarations:
            if "test-t" not in declaration:
                continue
            declaration_library = {
                name: result[name]
                for name in declaration.get("requires", [])
                if name in result
            }
            failure = runner.evaluate(
                declaration.get("transform-t"),
                declaration.get("test-t"),
                declaration_library,
            )
            if truthy(failure):
                failures.append(failure)
    return {"fail": failures} if failures else {"lib": result}
