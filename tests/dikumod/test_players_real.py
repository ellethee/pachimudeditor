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
    return _real_copy(request.param, tmp_path, read_only=None)


@pytest.fixture(params=("dikumod", "dikumod2"))
def real_rw(request: pytest.FixtureRequest, tmp_path: Path) -> tuple[DikumodAdapter, Path]:
    """Come `real_world` ma scrivibile (sempre e solo sulla copia temporanea)."""
    return _real_copy(request.param, tmp_path, read_only=False)


def _real_copy(variant: str, tmp_path: Path, *, read_only: bool | None) -> tuple[DikumodAdapter, Path]:
    """Copia di `lib/` con giocatori e rent reali (password azzerata) e l'adapter sulla copia."""
    from tests.dikumod_lib.conftest import copy_lib

    src = lib_of(variant)
    lib = copy_lib(variant, tmp_path)
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
    extra = {} if read_only is None else {"read_only": read_only}
    return DikumodAdapter(WorldConfig(id="dikumod", kind="dikumod", path=str(lib), params={"variant": variant}, **extra)), lib


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


async def test_real_players_roundtrip_through_the_writer(real_rw: tuple[DikumodAdapter, Path]) -> None:
    """Riscrivere ogni campo con il valore che si legge (e le tabelle) lascia il file reale identico; idem un rent riserializzato."""
    from pachimudeditor_adapter_dikumod.dikumod_lib.players_write import RentEditor, apply_char_patch

    adapter, lib = real_rw
    checked = rents = 0
    for path in sorted((lib / "players").glob("*.dat")):
        raw = path.read_bytes()
        detail = await adapter.get_player(path.stem)
        assert detail.problem is None
        writable = {k: v for k, v in detail.details.items() if k != "autoRent"}
        assert apply_char_patch(raw, {}, {}) == raw
        assert apply_char_patch(raw, writable, detail.lists) == raw, path.name
        checked += 1
        rent = lib / "rent" / path.stem
        if rent.is_file() and rent.stat().st_size >= 40 and (rent.stat().st_size - 40) % 592 == 0:
            rraw = rent.read_bytes()
            inv = await adapter.player_inventory(path.stem)
            if inv.problem is None:
                assert RentEditor(rraw, detail.name, gold=0, now=1).to_bytes() == rraw, path.name
                rents += 1
    assert checked >= 8 and rents >= 1


async def test_real_write_on_copies_only(real_rw: tuple[DikumodAdapter, Path]) -> None:
    """Scrittura vera (PATCH di campi, aggiunta/spostamento/rimozione di oggetti) su una copia di un giocatore reale."""
    from pachimudeditor.sdk import PlayerItemAdd, PlayerItemUpdate, PlayerPatch, PlayerWriteOptions

    adapter, lib = real_rw
    names = sorted(
        p.stem for p in (lib / "players").glob("*.dat") if (lib / "rent" / p.stem).is_file() and (lib / "rent" / p.stem).stat().st_size > 40
    )
    name = names[0]
    path, rent = lib / "players" / f"{name}.dat", lib / "rent" / name
    before, rent_before = path.read_bytes(), rent.read_bytes()
    detail = await adapter.get_player(name)
    out = await adapter.update_player(name, PlayerPatch(revision=detail.revision, details={"gold": 424242, "title": "Provato"}))
    assert out.gold == 424242 and out.details["title"] == "Provato" and out.level == detail.level
    new = path.read_bytes()
    assert (lib / "players" / f"{name}.dat.bak").read_bytes() == before and new[2974:2985] == before[2974:2985]
    assert {i for i, (a, b) in enumerate(zip(before, new, strict=True)) if a != b} <= {*range(48, 128), *range(676, 680)}  # titolo e oro
    inv = await adapter.player_inventory(name)
    plain = next(v for v, r in adapter.sync().objs.items() if r.item.type != 15 and 0 < v < 32768)
    added = await adapter.add_player_item(name, PlayerItemAdd(revision=inv.revision, vnum=plain))
    assert len(added.items) == len(inv.items) + 1 and added.problem is None
    moved = await adapter.update_player_item(name, len(added.items) - 1, PlayerItemUpdate(wear_slot="about"))
    assert moved.items[-1].wear_slot == "about"
    removed = await adapter.remove_player_item(name, len(moved.items) - 1, PlayerWriteOptions())
    assert [i.vnum for i in removed.items] == [i.vnum for i in inv.items] and removed.problem is None
    assert (lib / "rent" / f"{name}.bak").exists() and rent.read_bytes()[:20] == rent_before[:20]
