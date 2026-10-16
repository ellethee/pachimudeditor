"""CLI e template con adapter fittizi: kind installati, noti-ma-non-installati e relativi suggerimenti."""

import pytest
from typer.testing import CliRunner

from pachimudeditor.cli import app
from pachimudeditor.cli.helpers.templates import render_config
from pachimudeditor.cli.helpers.workdir import CONFIG_ENV, WORKDIR_ENV

runner = CliRunner(env={"COLUMNS": "250"})  # tabelle larghe: i suggerimenti non vanno a capo


def test_adapters_list(fake_plugins: None) -> None:
    """`adapters list` mostra i plugin scoperti e gli ufficiali mancanti con il comando per installarli."""
    result = runner.invoke(app, ["adapters", "list"])
    assert result.exit_code == 0, result.output
    assert "fake" in result.output and "installato" in result.output
    assert "non installato" in result.output and "pachimudeditor[dikumod]" in result.output


def test_init_template_has_examples_for_every_kind(fake_plugins: None) -> None:
    """Il `pachimudeditor.yaml` iniziale ha l'esempio dei plugin installati e il suggerimento per quelli mancanti."""
    text = render_config()
    assert "kind: fake" in text and "pachimudeditor[dikumod]" in text and "pachimudeditor[pachimud]" in text


def test_info_and_worlds_list_show_kinds(fake_plugins: None, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """`info` e `worlds list` riportano i kind disponibili e quelli da installare; senza mondi non falliscono."""
    monkeypatch.setenv(WORKDIR_ENV, str(tmp_path))
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    monkeypatch.delenv("WEBEDITOR_WORLDS", raising=False)
    monkeypatch.delenv("PACHIMUDEDITOR_WORLDS", raising=False)
    info = runner.invoke(app, ["info"])
    assert info.exit_code == 0 and "fake" in info.output and "pachimudeditor[dikumod]" in info.output
    listing = runner.invoke(app, ["worlds", "list"])
    assert listing.exit_code == 0 and "Kind disponibili: fake, fake2" in listing.output and "pachimudeditor[dikumod]" in listing.output


def test_worlds_check_unknown_kind_suggests_extra(fake_plugins: None, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Un mondo di un kind non installato: errore leggibile con l'extra da installare, exit code 1."""
    monkeypatch.setenv(WORKDIR_ENV, str(tmp_path))
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w", "kind": "dikumod", "path": "/x"}]')
    result = runner.invoke(app, ["worlds", "check"])
    assert result.exit_code == 1 and "pachimudeditor[dikumod]" in result.output
