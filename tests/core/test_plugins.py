"""Scoperta dei plugin degli adapter con entry point sintetici: nessun adapter reale e' necessario."""

import sys

import pytest

from pachimudeditor.common.adapters import plugins
from pachimudeditor.common.adapters.bootstrap import WorldSetupError, prepare_worlds
from pachimudeditor.common.adapters.convert.converter import get_converter
from pachimudeditor.common.adapters.convert.flavor import ComposedConverter
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry
from pachimudeditor.modules import build_modules
from tests.core.conftest import FAKE, entry_points


def test_discovery_registers_kinds(fake_plugins: None) -> None:
    """I kind dei plugin sono disponibili e il registro crea l'adapter con la factory del plugin."""
    assert plugins.available_kinds() == ["fake", "fake2"]
    registry = WorldRegistry([WorldConfig(id="w", kind="fake", name="W")])
    assert registry.get().describe().kind == "fake"


def test_nothing_heavy_imported_until_configured(fake_plugins: None) -> None:
    """Kind scoperti ma non configurati non importano factory, moduli o regole: solo il modulo `plugin`."""
    plugins.discover()
    assert f"{FAKE}.impl" not in sys.modules and f"{FAKE}.module" not in sys.modules
    assert "fake_adapter_module" not in {m.name for m in build_modules([])}
    assert f"{FAKE}.module" not in sys.modules


def test_modules_only_for_configured_kind(fake_plugins: None) -> None:
    """Il modulo API del plugin si aggiunge SOLO se e' configurato un mondo di quel kind."""
    assert "fake_adapter_module" in {m.name for m in build_modules(["fake"])}
    assert "fake_adapter_module" not in {m.name for m in build_modules(["fake2"])}


def test_unknown_kind_names_extra(fake_plugins: None) -> None:
    """Un kind ufficiale non installato dice quale extra installare; uno sconosciuto rimanda all'elenco."""
    with pytest.raises(ValueError, match=r"pachimudeditor\[dikumod\]"):
        WorldRegistry([WorldConfig(id="x", kind="dikumod")])
    with pytest.raises(ValueError, match="adapters list"):
        WorldRegistry([WorldConfig(id="x", kind="inventato")])


def test_broken_plugin_does_not_break_core(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un plugin che non si importa: avviso nel log, resto del core intatto, kind non disponibile con il motivo."""
    monkeypatch.setattr(
        plugins, "_entry_points", lambda: entry_points(fake=f"{FAKE}.plugin:plugin", dikumod=f"{FAKE}.broken_plugin:plugin")
    )
    plugins.reset_discovery()
    warnings: list[str] = []
    monkeypatch.setattr(plugins.log, "warning", lambda msg, *args: warnings.append(msg % args))
    records = plugins.discover()
    assert records["fake"].ok and not records["dikumod"].ok and "modulo_inesistente" in records["dikumod"].error
    assert any("'dikumod'" in w and "non utilizzabile" in w for w in warnings) and plugins.available_kinds() == ["fake"]
    assert build_modules(["dikumod", "fake"])  # nessuna eccezione
    with pytest.raises(ValueError, match="non si carica"):
        WorldRegistry([WorldConfig(id="x", kind="dikumod")])
    plugins.reset_discovery()


def test_wrong_entry_point_name_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Il nome dell'entry point deve coincidere col kind del plugin."""
    monkeypatch.setattr(plugins, "_entry_points", lambda: entry_points(altro=f"{FAKE}.plugin:plugin"))
    plugins.reset_discovery()
    assert "non coincide" in plugins.discover()["altro"].error
    plugins.reset_discovery()


def test_flavors_compose_across_plugins(fake_plugins: None) -> None:
    """La coppia di convertitori si compone dai sapori dei due plugin; senza sapori resta il ripiego generico."""
    assert isinstance(get_converter("fake", "fake2"), ComposedConverter)
    assert get_converter("fake", "mai_visto").generic


def test_validate_runs_at_startup(fake_plugins: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """La `validate` del plugin dà un errore di avvio leggibile; con parametri giusti l'avvio passa."""
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w", "kind": "fake"}]')
    with pytest.raises(WorldSetupError, match="manca path"):
        prepare_worlds()
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w", "kind": "fake", "path": "/x"}]')
    assert [c.id for c in prepare_worlds()[0]] == ["w"]
    monkeypatch.setenv("WEBEDITOR_WORLDS", '[{"id": "w", "kind": "dikumod"}]')
    with pytest.raises(WorldSetupError, match=r"pachimudeditor\[dikumod\]"):
        prepare_worlds()


def test_sdk_major_mismatch_is_rejected_minor_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """Major diversa (piu' nuova o piu' vecchia): kind in errore con messaggio chiaro, niente crash; minor diversa: compatibile."""
    monkeypatch.setattr(
        plugins,
        "_entry_points",
        lambda: entry_points(
            sdk_next=f"{FAKE}.plugin:plugin_sdk_next_major",
            sdk_old=f"{FAKE}.plugin:plugin_sdk_old_major",
            sdk_newer=f"{FAKE}.plugin:plugin_sdk_newer_minor",
            sdk_older=f"{FAKE}.plugin:plugin_sdk_older_minor",
            fake=f"{FAKE}.plugin:plugin",  # senza sdk_version: nessun controllo (adapter datati)
        ),
    )
    plugins.reset_discovery()
    records = plugins.discover()
    assert plugins.available_kinds() == ["fake", "sdk_newer", "sdk_older"]
    for kind in ("sdk_next", "sdk_old"):
        assert not records[kind].ok and "SDK incompatibile" in records[kind].error
        with pytest.raises(plugins.AdapterUnavailable, match="SDK incompatibile"):
            WorldRegistry([WorldConfig(id="x", kind=kind)])
    assert {s.kind: s.state for s in plugins.kind_statuses() if s.kind.startswith("sdk")}["sdk_next"] == "broken"
    plugins.reset_discovery()
