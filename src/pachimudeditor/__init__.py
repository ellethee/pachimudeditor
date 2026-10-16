"""Webeditor di pachimud: backend pachifast + frontend Quasar impacchettato, con CLI `pachimudeditor`."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pachimudeditor")
except PackageNotFoundError:  # sorgenti non installati
    __version__ = "0.0.0+unknown"
