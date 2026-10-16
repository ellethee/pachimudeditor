"""DSL di espressioni: operazioni ammesse e rifiuto di tutto cio' che e' codice Python arbitrario."""

import pytest
from pachimudeditor_adapter_mapping.dsl import ExprError, evaluate, names_in


@pytest.mark.parametrize(
    ("source", "env", "expected"),
    [
        ("20 - hitroll", {"hitroll": 5}, 15),
        ("limit if limit >= 0 else None", {"limit": -1}, None),
        ("max(limit, 0)", {"limit": -3}, 0),
        ("(real_sector if sector == -1 else sector) in [7, 9]", {"sector": -1, "real_sector": 9}, True),
        ("has_flag(flags, 256) and not has_flag(flags, 2)", {"flags": 257}, True),
        ("(exit_info & ~33) | (33 if value == 'PICKPROOF' else 0)", {"exit_info": 39, "value": "PICKPROOF"}, 6 | 33),
        ("int_or_none(values[0])", {"values": ["12", "x"]}, 12),
        ("int_or_none(values[1])", {"values": ["12", "x"]}, None),
        ("missing is None", {}, True),
        ("get(hit, 'n', 1)", {"hit": {"n": 4}}, 4),
        ("re_group(credits, '^\\\\s*\\\\{\\\\s*(\\\\d+)', 1, '1')", {"credits": "{ 5 35 } Foo"}, "5"),
        ("lower(strip(name)) + '!'", {"name": "  ABC "}, "abc!"),
        ("a < 3", {"a": None}, False),  # confronto impossibile: falso, non eccezione
    ],
)
def test_expressions(source: str, env: dict, expected: object) -> None:
    """Espressioni tipiche delle mappature."""
    assert evaluate(source, env) == expected


@pytest.mark.parametrize(
    "source",
    [
        "__import__('os').system('true')",
        "open('/etc/passwd')",
        "().__class__",
        "x.__class__",
        "(lambda: 1)()",
        "[a for a in range(3)]",
        "f'{x}'",
        "x ** 99",
        "eval('1')",
        "x := 3",
        "int(x, base=2)",
        "1 +",
    ],
)
def test_rejects_arbitrary_code(source: str) -> None:
    """Nessun accesso a import, builtin non in lista, attributi, lambda, comprehension, f-string o potenze."""
    with pytest.raises(ExprError):
        evaluate(source, {"x": 1})


def test_names_in_ignores_functions() -> None:
    """`names_in` elenca i campi usati (per i controlli incrociati del caricamento), non le funzioni."""
    assert names_in("max(limit, 0) + (a if b else c)") == {"limit", "a", "b", "c"}
