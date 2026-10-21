"""Validazione di `params.live` del mondo dikumod: parametri incoerenti = errore all'avvio; MUD spento o token non impostato = no."""

import json
from pathlib import Path
from typing import Any

import pytest

from pachimudeditor.common.adapters.bootstrap import WorldSetupError, prepare_worlds
from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor_adapter_dikumod.live_config import parse_live_settings, validate_world

OK: dict[str, Any] = {"socket": "/tmp/non-esiste/livectl.sock", "token_env": "QUALCOSA_TOKEN"}


def test_valid_config_does_not_need_a_running_mud(monkeypatch: pytest.MonkeyPatch) -> None:
    """Socket inesistente e variabile del token non impostata non sono errori: il canale e' opzionale."""
    monkeypatch.delenv("QUALCOSA_TOKEN", raising=False)
    validate_world(WorldConfig(id="w", kind="dikumod", params={"live": OK}))
    settings = parse_live_settings({"live": OK})
    assert settings is not None and settings.timeout_ms == 3000 and settings.token_env == "QUALCOSA_TOKEN"


def test_absent_or_disabled_means_no_live() -> None:
    """Senza `live` o con `enabled: false` il mondo non ha il canale."""
    assert parse_live_settings({}) is None
    assert parse_live_settings({"live": {**OK, "enabled": False}}) is None


@pytest.mark.parametrize(
    "live",
    [
        "stringa", {**OK, "socket": "relativo.sock"}, {**OK, "socket": "/" + "a" * 120}, {**OK, "socket": None}, {**OK, "token_env": "con spazio"},
        {**OK, "token_env": "a" * 5 + "-b"}, {"socket": OK["socket"]}, {**OK, "timeout_ms": 10}, {**OK, "timeout_ms": True}, {**OK, "enabled": "si"},
        {**OK, "transport": "tcp"}, {**OK, "token": "segreto-nel-yaml"}, {**OK, "sconosciuto": 1},
    ],
)  # fmt: skip
def test_incoherent_params_are_rejected(live: Any) -> None:
    """Percorso relativo o troppo lungo, nome di variabile non valido, timeout fuori scala, TCP, chiavi sconosciute (anche un `token` nel yaml)."""
    with pytest.raises(ValueError, match="params.live"):
        parse_live_settings({"live": live})


def test_startup_reports_a_clear_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """All'avvio (`prepare_worlds`) un mondo con `live` incoerente e' un `WorldSetupError` che nomina il mondo."""
    world = {"id": "diku", "kind": "dikumod", "path": str(tmp_path), "params": {"live": {**OK, "socket": "relativo"}}}
    monkeypatch.setenv("WEBEDITOR_WORLDS", json.dumps([world]))
    with pytest.raises(WorldSetupError, match="diku"):
        prepare_worlds()
