"""Confini del monorepo (scansioni AST dei sorgenti): nessun adapter richiesto per eseguirli."""

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = PACKAGE_ROOT / "src" / "pachimudeditor"
SOURCES = [CORE_SRC, *sorted(PACKAGE_ROOT.glob("adapters/*/src/pachimudeditor_adapter_*"))]
"""Il core e il pacchetto sorgente di ogni adapter del monorepo."""


def test_package_never_imports_pachimud() -> None:
    """Scansione AST di core e adapter: nessun `import pachimud` / `from pachimud...` (solo `pachimudeditor*`)."""
    offenders: list[str] = []
    for path in sorted(p for root in SOURCES for p in root.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) in ("import_module", "__import__"):
                names = [arg.value for arg in node.args[:1] if isinstance(arg, ast.Constant) and isinstance(arg.value, str)]
            offenders += [f"{path.relative_to(PACKAGE_ROOT)}:{node.lineno} {name}" for name in names if name.split(".")[0] == "pachimud"]
    assert not offenders, offenders


def test_no_sys_path_tricks_or_python_path() -> None:
    """Niente `sys.path`, `python_path` o `PACHIMUD_CONFIG_PATH` nei sorgenti (salvo il ripiego documentato in params.py)."""
    pyproject = (PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "python_path" not in pyproject
    for path in (p for root in SOURCES for p in root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "sys.path" not in text, path
        if "PACHIMUD_CONFIG_PATH" in text:
            assert path.name == "params.py", path


def _imported_modules(path: Path) -> list[tuple[int, str]]:
    """`(riga, modulo)` di ogni import assoluto del file."""
    out: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [(node.lineno, a.name) for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append((node.lineno, node.module))
    return out


def test_core_never_imports_adapters() -> None:
    """Il core non importa nessun pacchetto adapter (`pachimudeditor_adapter_*`): li scopre con gli entry point."""
    offenders = [
        f"{p.relative_to(CORE_SRC)}:{line} {mod}"
        for p in sorted(CORE_SRC.rglob("*.py"))
        for line, mod in _imported_modules(p)
        if mod.startswith("pachimudeditor_adapter")
    ]
    assert not offenders, offenders


PUBLIC_CORE_MODULES = {
    "pachimudeditor.sdk",
    "pachimudeditor.common.adapters.models",
    "pachimudeditor.common.adapters.convert.helpers",
    "pachimudeditor.common.enums",
}
"""Le uniche parti del core che un adapter puo' importare (l'API pubblica, vedi docs/adapters/index.md)."""


def test_adapters_use_only_public_core_api() -> None:
    """Ogni adapter importa dal core solo l'API pubblica; tra adapter diversi non ci sono dipendenze."""
    offenders: list[str] = []
    for root in SOURCES[1:]:
        own = root.name
        for p in sorted(root.rglob("*.py")):
            for line, mod in _imported_modules(p):
                head = mod.split(".")[0]
                bad_core = head == "pachimudeditor" and mod not in PUBLIC_CORE_MODULES
                bad_other = head.startswith("pachimudeditor_adapter_") and head != own
                if bad_core or bad_other:
                    offenders.append(f"{p.relative_to(PACKAGE_ROOT)}:{line} {mod}")
    assert not offenders, offenders
