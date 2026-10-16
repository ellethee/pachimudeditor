"""CLI `pachimudeditor`: risoluzione della cartella di lavoro, template di config e indirizzo di serve."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from pachimudeditor.cli import app
from pachimudeditor.cli.commands.serve import resolve_address
from pachimudeditor.cli.helpers.templates import render_config
from pachimudeditor.cli.helpers.workdir import CONFIG_ENV, WORKDIR_ENV, resolve_workdir

runner = CliRunner()


def test_version() -> None:
    """`--version` stampa il nome e la versione."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and result.output.startswith("pachimudeditor ")


def test_resolve_workdir_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """L'opzione batte la variabile d'ambiente, che batte la cartella corrente."""
    monkeypatch.setenv(WORKDIR_ENV, str(tmp_path))
    assert resolve_workdir() == tmp_path.resolve()
    assert resolve_workdir(tmp_path / "x") == (tmp_path / "x").resolve()


def test_config_template_is_valid_for_pachifast(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Il template generato da `init` e' accettato da pachifast (sezioni valide) e porta i mondi e la config di gioco."""
    from pachifast.config.yaml_source import load_config_data

    from pachimudeditor.common.adapters.settings import load_world_settings

    config = tmp_path / "pachimudeditor.yaml"
    config.write_text(render_config(), encoding="utf-8")
    monkeypatch.setenv(CONFIG_ENV, str(config))
    monkeypatch.delenv("WEBEDITOR_WORLDS", raising=False)
    monkeypatch.delenv("PACHIMUDEDITOR_WORLDS", raising=False)
    monkeypatch.delenv("WEBEDITOR_DEFAULT_WORLD", raising=False)
    data = load_config_data()
    assert data["port"] == 8123 and data["default_locale"] == "it"
    worlds, default = load_world_settings()
    assert worlds is None and default is None  # nessun mondo implicito: solo esempi commentati


def test_env_alias_for_worlds(monkeypatch: pytest.MonkeyPatch) -> None:
    """`PACHIMUDEDITOR_WORLDS` e' un alias di `WEBEDITOR_WORLDS` (che ha la precedenza)."""
    from pachimudeditor.common.adapters.settings import load_world_settings

    monkeypatch.delenv("WEBEDITOR_WORLDS", raising=False)
    monkeypatch.setenv("PACHIMUDEDITOR_WORLDS", '[{"id": "a", "kind": "pachimud"}]')
    assert load_world_settings()[0] == [{"id": "a", "kind": "pachimud"}]
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "b", "kind": "pachimud"}]')
    assert load_world_settings()[0] == [{"id": "b", "kind": "pachimud"}]


def test_resolve_address_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Senza opzioni ne' config: 127.0.0.1:8123; le opzioni vincono."""
    monkeypatch.setenv(CONFIG_ENV, str(tmp_path / "assente.yaml"))
    monkeypatch.delenv(CONFIG_ENV)
    monkeypatch.chdir(tmp_path)
    for var in ("PACHIFAST_HOST", "PACHIFAST_PORT"):
        monkeypatch.delenv(var, raising=False)
    assert resolve_address(None, None) == ("127.0.0.1", 8123)
    assert resolve_address("0.0.0.0", 9000) == ("0.0.0.0", 9000)
