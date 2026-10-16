"""Mini-linguaggio di espressioni sicuro per i file di mappatura (niente `eval`/`exec` di Python arbitrario).

Un'espressione e' parsata con `ast` e ammessa solo se composta da: costanti, nomi (i campi del record e `value`),
operatori aritmetici/bit a bit/logici/di confronto, `a if c else b`, indici `x[0]`, liste/tuple/dict letterali e
chiamate alle funzioni della lista bianca `FUNCTIONS` (nessun attributo, nessun import, nessun lambda).

Un nome mancante nel record vale `None` (cosi' i campi opzionali si testano con `x is None`).
"""

import ast
import re
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any


class ExprError(ValueError):
    """Espressione non valida (sintassi o costrutto non ammesso)."""


def _int_or_none(x: Any) -> int | None:
    """`int(x)` se `x` e' un decimale (anche stringa), altrimenti `None`."""
    try:
        return int(str(x).strip())
    except TypeError, ValueError:
        return None


def _get(obj: Any, path: str, default: Any = None) -> Any:
    """Valore a `path` (`a.b.0`) dentro dict/liste annidati, `default` se manca."""
    for part in str(path).split("."):
        try:
            obj = obj[int(part)] if isinstance(obj, list | tuple) else obj[part]
        except KeyError, IndexError, TypeError, ValueError:
            return default
    return obj


def _re_group(text: Any, pattern: str, group: int = 1, default: Any = "") -> Any:
    """Gruppo `group` della prima corrispondenza di `pattern` in `text` (`default` se non c'e')."""
    m = re.search(pattern, "" if text is None else str(text))
    return m.group(group) if m else default


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
    "len": len,
    "min": min,
    "max": max,
    "abs": abs,
    "strip": lambda s: ("" if s is None else str(s)).strip(),
    "lower": lambda s: ("" if s is None else str(s)).lower(),
    "upper": lambda s: ("" if s is None else str(s)).upper(),
    "split": lambda s, sep=None: ("" if s is None else str(s)).split(sep),
    "join": lambda sep, items: str(sep).join(str(i) for i in items),
    "replace": lambda s, a, b: ("" if s is None else str(s)).replace(a, b),
    "startswith": lambda s, p: ("" if s is None else str(s)).startswith(p),
    "get": _get,
    "int_or_none": _int_or_none,
    "re_group": _re_group,
    "re_sub": lambda text, pattern, repl: re.sub(pattern, repl, "" if text is None else str(text), count=1),
    "has_flag": lambda value, bit: bool((value or 0) & bit),
    "set_flag": lambda value, bit, on=True: ((value or 0) | bit) if on else ((value or 0) & ~bit),
}
"""Funzioni richiamabili dalle espressioni (lista bianca)."""

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.BitAnd: lambda a, b: a & b,
    ast.BitOr: lambda a, b: a | b,
    ast.BitXor: lambda a, b: a ^ b,
    ast.LShift: lambda a, b: a << b,
    ast.RShift: lambda a, b: a >> b,
}
_UNARY: dict[type, Callable[[Any], Any]] = {
    ast.Not: lambda a: not a,
    ast.USub: lambda a: -a,
    ast.UAdd: lambda a: +a,
    ast.Invert: lambda a: ~a,
}
_CMPS: dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: lambda a, b: a == b,
    ast.NotEq: lambda a, b: a != b,
    ast.Lt: lambda a, b: a < b,
    ast.LtE: lambda a, b: a <= b,
    ast.Gt: lambda a, b: a > b,
    ast.GtE: lambda a, b: a >= b,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: lambda a, b: a is b,
    ast.IsNot: lambda a, b: a is not b,
}


_ALLOWED = (
    ast.Constant, ast.Name, ast.Load, ast.BoolOp, ast.And, ast.Or, ast.BinOp, ast.UnaryOp, ast.Compare, ast.IfExp,
    ast.Subscript, ast.Slice, ast.List, ast.Tuple, ast.Dict, ast.Call, *_BINOPS, *_UNARY, *_CMPS,
)  # fmt: skip
"""Unici nodi dell'albero ammessi: tutto il resto (comprehension, attributi, lambda, f-string, ...) e' rifiutato."""


@lru_cache(maxsize=2048)
def compile_expr(source: str) -> ast.expr:
    """Parsa e valida `source`; solleva `ExprError` se contiene costrutti non ammessi."""
    try:
        tree = ast.parse(source.strip(), mode="eval").body
    except SyntaxError as error:
        raise ExprError(f"sintassi non valida in {source!r}: {error.msg}") from error
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ExprError(f"costrutto non ammesso in {source!r}: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise ExprError(f"chiamata non ammessa in {source!r} (funzioni: {', '.join(sorted(FUNCTIONS))})")
    return tree


def names_in(source: str) -> set[str]:
    """I nomi (campi) usati da un'espressione, funzioni escluse."""
    tree = compile_expr(source)
    called = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - called - {"True", "False", "None"}


def _ev(node: ast.expr, env: Mapping[str, Any]) -> Any:
    """Valuta un nodo gia' validato."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[node.id]
        return env.get(node.id)
    if isinstance(node, ast.BoolOp):
        result: Any = None
        for value in node.values:
            result = _ev(value, env)
            if isinstance(node.op, ast.And) and not result:
                return result
            if isinstance(node.op, ast.Or) and result:
                return result
        return result
    if isinstance(node, ast.BinOp):
        return _BINOPS[type(node.op)](_ev(node.left, env), _ev(node.right, env))
    if isinstance(node, ast.UnaryOp):
        return _UNARY[type(node.op)](_ev(node.operand, env))
    if isinstance(node, ast.Compare):
        left = _ev(node.left, env)
        for op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _ev(comparator, env)
            try:
                ok = _CMPS[type(op)](left, right)
            except TypeError:  # es. `None < 3`: il confronto fallisce senza far cadere la richiesta
                ok = False
            if not ok:
                return False
            left = right
        return True
    if isinstance(node, ast.IfExp):
        return _ev(node.body if _ev(node.test, env) else node.orelse, env)
    if isinstance(node, ast.Subscript):
        target, index = _ev(node.value, env), _ev(node.slice, env)
        try:
            return target[index]
        except KeyError, IndexError, TypeError:
            return None
    if isinstance(node, ast.Slice):
        return slice(*(None if p is None else _ev(p, env) for p in (node.lower, node.upper, node.step)))
    if isinstance(node, ast.List | ast.Tuple):
        return [_ev(e, env) for e in node.elts]
    if isinstance(node, ast.Dict):
        return {_ev(k, env): _ev(v, env) for k, v in zip(node.keys, node.values, strict=True) if k is not None}
    if isinstance(node, ast.Call):
        return FUNCTIONS[node.func.id](*(_ev(a, env) for a in node.args))  # type: ignore[attr-defined]
    raise ExprError(f"nodo non valutabile: {type(node).__name__}")


def evaluate(source: str, env: Mapping[str, Any]) -> Any:
    """Valuta `source` con i nomi di `env` (i mancanti valgono `None`)."""
    return _ev(compile_expr(source), env)


__all__ = ["FUNCTIONS", "ExprError", "compile_expr", "evaluate", "names_in"]
