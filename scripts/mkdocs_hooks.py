"""Hook di MkDocs: porta nel sito CHANGELOG.md e RELEASING.md (che restano alla radice) e la versione del core."""

import tomllib
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files

ROOT = Path(__file__).resolve().parent.parent
PAGES = {"changelog.md": "CHANGELOG.md", "releasing.md": "RELEASING.md"}


def on_files(files: Files, config: MkDocsConfig) -> Files:
    """Aggiunge al sito le pagine generate leggendo i file della radice."""
    for dest, src in PAGES.items():
        text = (ROOT / src).read_text(encoding="utf-8")
        files.append(File.generated(config, dest, content=text))
    return files


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Legge la versione da pyproject.toml: va nel footer (`copyright`) e nella home (`extra.version`)."""
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    config.extra["version"] = version
    config.copyright = f"pachimudeditor {version} &middot; MIT License &middot; alpha"
    return config
