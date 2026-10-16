#!/usr/bin/env python3
"""Controlli di rilascio usati dal workflow `publish-pypi.yml` (e provabili in locale).

Uso:
    release_check.py tag <TAG>            # es. pachimudeditor-adapter-dikumod-v0.2.0: stampa package/version/directory (GITHUB_OUTPUT)
    release_check.py package <NOME>       # come sopra ma la versione viene dal pyproject (rilascio manuale su TestPyPI)
    release_check.py wheel <NOME> <DIST>  # controlla il contenuto di wheel e sdist gia' costruiti in <DIST>
Esce con 1 e un messaggio chiaro al primo problema.
"""

from __future__ import annotations

import re
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = "pachimudeditor"
TAG_RE = re.compile(r"^(pachimudeditor(?:-adapter-[a-z0-9]+)?)-v(\d+\.\d+\.\d+)$")
PRIVATE = "Private :: Do Not Upload"


class ReleaseError(Exception):
    """Un controllo di rilascio e' fallito."""


def parse_tag(tag: str) -> tuple[str, str]:
    """Ricava (pacchetto, versione) da un tag `<pacchetto>-vX.Y.Z`."""
    m = TAG_RE.match(tag.removeprefix("refs/tags/"))
    if not m:
        raise ReleaseError(f"tag '{tag}' non valido: atteso <pacchetto>-vX.Y.Z (es. {CORE}-v0.1.0)")
    return m.group(1), m.group(2)


def package_dir(package: str, root: Path = ROOT) -> Path:
    """Cartella del pacchetto nel monorepo (il core e' la radice, gli adapter stanno in adapters/<kind>)."""
    if package == CORE:
        return root
    d = root / "adapters" / package.removeprefix(f"{CORE}-adapter-")
    if not (d / "pyproject.toml").is_file():
        raise ReleaseError(f"pacchetto '{package}' sconosciuto: manca {d / 'pyproject.toml'}")
    return d


def load_project(package: str, root: Path = ROOT) -> dict:
    """Sezione [project] del pyproject del pacchetto, verificando che il nome coincida."""
    project = tomllib.loads((package_dir(package, root) / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if project["name"] != package:
        raise ReleaseError(f"il pyproject di '{package}' dichiara il nome '{project['name']}'")
    return project


def check_release(package: str, version: str | None, root: Path = ROOT) -> str:
    """Verifica versione (se indicata) e classificatore Private; ritorna la versione del pyproject."""
    project = load_project(package, root)
    if version is not None and project["version"] != version:
        raise ReleaseError(
            f"il tag dice {version} ma {package} ha versione {project['version']} nel pyproject.toml: "
            "aggiorna la versione (e uv lock) prima di taggare"
        )
    if PRIVATE in project.get("classifiers", []):
        raise ReleaseError(
            f"{package} ha ancora il classificatore '{PRIVATE}' (PyPI rifiuterebbe l'upload): "
            "toglierlo come descritto in RELEASING.md prima del primo rilascio"
        )
    return project["version"]


def check_dist(package: str, dist: Path, root: Path = ROOT) -> None:
    """Controlla che in `dist` ci siano wheel e sdist del pacchetto; il wheel del core deve contenere la SPA."""
    version = load_project(package, root)["version"]
    norm = package.replace("-", "_")
    wheels = sorted(dist.glob(f"{norm}-{version}-*.whl"))
    if len(wheels) != 1:
        raise ReleaseError(f"atteso un wheel {norm}-{version}-*.whl in {dist}, trovati {len(wheels)}")
    if not (dist / f"{norm}-{version}.tar.gz").is_file():
        raise ReleaseError(f"manca lo sdist {norm}-{version}.tar.gz in {dist}")
    if package == CORE:
        names = zipfile.ZipFile(wheels[0]).namelist()
        if "pachimudeditor/static/index.html" not in names:
            raise ReleaseError("il wheel del core non contiene pachimudeditor/static/index.html: build del frontend mancante")


def main(argv: list[str]) -> int:
    """Entry point CLI; stampa `chiave=valore` adatti a $GITHUB_OUTPUT."""
    try:
        cmd, *args = argv
        if cmd == "tag" and len(args) == 1:
            package, version = parse_tag(args[0])
        elif cmd == "package" and len(args) == 1:
            package, version = args[0], None
        elif cmd == "wheel" and len(args) == 2:
            check_dist(args[0], Path(args[1]))
            print("ok")
            return 0
        else:
            print(__doc__)
            return 2
        version = check_release(package, version)
        print(f"package={package}\nversion={version}\ndirectory={package_dir(package).relative_to(ROOT) or '.'}")
        return 0
    except (ReleaseError, ValueError) as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
