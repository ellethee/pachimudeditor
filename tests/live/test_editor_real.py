"""L'adapter dikumod dell'editor contro il MUD REALE (Diku Modificato `leu` con il modulo `livectl`, su copie in /tmp).

Come `tests/live`: serve la cartella `leu` (o `DIKUMOD_SRC`/`DIKUMOD_LIB`), g++ e make; altrimenti si salta. Il prefisso dei file dati e'
`DIKUMOD_PREFIX` (default `leudata`). Il giocatore `Tester` e' creato e fatto entrare da `real_mud`.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator

import pytest

from pachimudeditor.common.adapters.registry import WorldConfig
from pachimudeditor.sdk import LiveEchoIn, LiveError, LiveLoadIn, LivePlayerSetIn, LiveZoneResetIn, PlayerPageParams
from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from tests.live import real_mud
from tests.support import real_data

pytestmark = pytest.mark.skipif(real_mud.available() is not None, reason=real_mud.available() or "")
ENV = "EDITOR_REAL_LIVE_TOKEN"


@pytest.fixture(scope="module")
async def mud() -> AsyncIterator[real_mud.RealMud]:
    """Il MUD acceso su una copia temporanea (si compila una volta per modulo)."""
    running = await real_mud.start()
    yield running
    running.stop()


@pytest.fixture
async def adapter(mud: real_mud.RealMud, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[DikumodAdapter]:
    """L'adapter dell'editor sulla `lib` del MUD, col canale live configurato (token solo nell'ambiente)."""
    monkeypatch.setenv(ENV, real_mud.TOKEN)
    config = WorldConfig(
        id="real", kind="dikumod", path=str(mud.root / "lib"), read_only=False,
        params={"data_prefix": real_data.DIKUMOD_PREFIX, "live": {"socket": mud.socket, "token_env": ENV}},
    )  # fmt: skip
    live = DikumodAdapter(config)
    yield live
    await live.close()


async def test_status_who_and_players_online(adapter: DikumodAdapter) -> None:
    """Il modulo C risponde a `hello`; `Tester` e' connesso e i giocatori su file lo vedono `online`, gli altri no."""
    status = await adapter.live_status()
    assert status.state == "connected" and status.mud.get("module", "").startswith("livectl") and "player.set" in status.commands
    assert "Tester" in {p.name for p in (await adapter.live_who()).players}
    assert (await adapter.get_player("tester")).online is True
    assert (await adapter.player_connected("tester")) is True
    others = [p for p in (await adapter.list_players(PlayerPageParams())).items if p.id != "tester"]
    assert others and all(p.online is False for p in others)
    assert (await adapter.players_status()).detection == "live"


async def test_live_edit_saves_the_player_file(adapter: DikumodAdapter, mud: real_mud.RealMud) -> None:
    """`player.set` col salvataggio del gioco: la memoria cambia, il file `players/tester.dat` pure (letto dall'editor)."""
    before = (mud.root / "lib" / "players" / "tester.dat").stat().st_mtime
    time.sleep(1.1)  # risoluzione di mtime: un secondo
    out = await adapter.live_player_set("tester", LivePlayerSetIn(fields={"gold": 4242}), actor="pytest")
    assert out.saved and out.applied["gold"].new == 4242
    assert (await adapter.live_player_get("tester")).fields["gold"] == 4242
    assert (mud.root / "lib" / "players" / "tester.dat").stat().st_mtime > before
    assert (await adapter.get_player("tester")).details["gold"] == 4242
    with pytest.raises(LiveError) as info:
        await adapter.live_player_set("tester", LivePlayerSetIn(fields={"levels": {"cleric": 55}}))
    assert info.value.code == "forbidden_by_policy" and info.value.params["reason"] == "immortal_level"
    assert (await adapter.live_player_get("tester")).fields["levels"] == {"cleric": 3}
    with pytest.raises(LiveError) as range_error:
        await adapter.live_player_set("tester", LivePlayerSetIn(fields={"str": 99}))
    assert range_error.value.code == "value_out_of_range"
    assert mud.audit.read_text().count("actor=pytest") >= 1


async def test_zone_load_and_echo(adapter: DikumodAdapter) -> None:
    """Reset di una zona scelta dall'elenco del gioco, creazione di un mob nella stanza di Tester, messaggio, deny-list."""
    zones = (await adapter.live_zones()).zones
    assert len(zones) > 5
    zone = next(z for z in zones if z.index > 0)
    assert (await adapter.live_zone_reset(LiveZoneResetIn(zone=zone.index), actor="pytest")).zone == zone.index
    with pytest.raises(LiveError) as zone0:
        await adapter.live_zone_reset(LiveZoneResetIn(zone=0))
    assert zone0.value.params["reason"] == "zone_zero"
    assert (await adapter.live_echo(LiveEchoIn(text="Prova dall'editor", player="Tester"), actor="pytest")).recipients == 1
    mob = next(iter(adapter.sync().mobs))  # un vnum di mob che esiste nel mondo
    loaded = await adapter.live_load("mob", LiveLoadIn(vnum=mob, player="Tester"), actor="pytest")
    assert len(loaded.loaded) == 1
    with pytest.raises(LiveError) as denied:
        await adapter.live_load("obj", LiveLoadIn(vnum=1600, player="Tester"))
    assert denied.value.params["reason"] == "deny_list"
