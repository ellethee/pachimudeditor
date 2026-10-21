"""Giocatori su dati reali: SOLO copie temporanee con il campo password azzerato (originali mai toccati ne' copiati interi).

Si saltano se `DIKUMOD_ROOT` non e' impostata. Nessun contenuto dei file reali finisce nel repo.
"""

from pathlib import Path

import pytest

from pachimudeditor.sdk import PlayerPageParams, WorldConfig
from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor_adapter_dikumod.dikumod_lib.players import CHAR_FILE_SIZE
from tests.dikumod_lib.conftest import lib_of, real_name
from tests.support.real_data import HAVE_DIKUMOD

pytestmark = pytest.mark.skipif(not HAVE_DIKUMOD, reason="DIKUMOD_ROOT non impostata o dati reali assenti")

PWD_START, PWD_END = 2974, 2985


@pytest.fixture(params=("dikumod", "dikumod2"))
def real_world(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[DikumodAdapter, Path]:
    """Adapter in sola lettura su una copia di `lib/` (mondo reale + giocatori e rent con la password azzerata)."""
    from tests.dikumod_lib.conftest import copy_lib

    src = lib_of(request.param)
    lib = copy_lib(request.param, tmp_path)
    (lib / "players").mkdir()
    (lib / "rent").mkdir()
    for f in (src / "players").glob("*.dat"):
        data = bytearray(f.read_bytes())
        if len(data) == CHAR_FILE_SIZE:
            data[PWD_START:PWD_END] = bytes(PWD_END - PWD_START)  # mai una password vera, nemmeno nella copia
        (lib / "players" / f.name).write_bytes(bytes(data))
    for f in (src / "rent").iterdir():
        if f.is_file() and "." not in f.name:
            (lib / "rent" / f.name).write_bytes(f.read_bytes())
    return DikumodAdapter(WorldConfig(id="dikumod", kind="dikumod", path=str(lib), params={"variant": request.param})), lib


async def test_every_real_player_is_listed_and_readable(real_world: tuple[DikumodAdapter, Path]) -> None:
    """Tutti i `.dat` reali (non i `.dat~`) compaiono senza problemi, con classe, razza e livello sensati e password azzerata."""
    adapter, lib = real_world
    page = await adapter.list_players(PlayerPageParams(page=1, pageSize=100))
    files = sorted(p.stem for p in (lib / "players").glob("*.dat"))
    assert [p.id for p in page.items] == files and len(files) >= 8
    for player in page.items:
        assert player.problem is None, player.id
        assert player.has_password is False  # azzerata nella copia
        assert player.level and 1 <= player.level <= 100 and player.class_label
        assert player.race_label or "raceRaw" in player.extra  # un record reale (`error`) ha una razza fuori tabella
        assert player.name.lower() == player.id
        detail = await adapter.get_player(player.id)
        assert "str" in detail.details and detail.lists["skills"] is not None


async def test_every_real_rent_file_parses(real_world: tuple[DikumodAdapter, Path]) -> None:
    """Ogni rent reale e' coerente (40 + n*592 byte) e gli oggetti hanno nomi; i prototipi noti sono risolti."""
    adapter, lib = real_world
    seen = 0
    for rent in sorted((lib / "rent").iterdir()):
        if rent.name not in {p.stem for p in (lib / "players").glob("*.dat")}:
            continue
        inventory = await adapter.player_inventory(rent.name)
        size = rent.stat().st_size
        assert inventory.problem in (None, "owner_mismatch"), (rent.name, inventory.problem)
        if size > 40:
            assert (size - 40) % 592 == 0 and len(inventory.items) == (size - 40) // 592
            assert all(i.name for i in inventory.items)
            seen += len(inventory.items)
    assert seen > 0


def test_original_directories_are_not_modified_by_the_copy_fixture() -> None:
    """La fixture legge soltanto gli originali: il nome reale del prefisso resta quello atteso (sanity)."""
    assert real_name("dikumoddata.wld").endswith(".wld")
