"""Procedure speciali dei mob da `spec_assign.c` (sola lettura): parser, adapter sul mondo sintetico e dati reali di leu."""

import os
import re
from pathlib import Path

import httpx  # noqa: TC002
import pytest
from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from pachimudeditor_adapter_dikumod.specials import (
    MAX_BYTES,
    TEACHING_PROCS,
    SpecAssign,
    SpecAssignError,
    parse_spec_assign,
    read_spec_assign,
)

from pachimudeditor.common.adapters import registry as registry_module
from pachimudeditor.common.adapters.models import MobPageParams
from pachimudeditor.common.adapters.registry import WorldConfig, WorldRegistry, set_registry
from tests.helpers import data
from tests.support import stack
from tests.support import real_data
from tests.support.synthetic_worlds import write_dikumod_world

TABLE = """\
static struct special_proc_entry specials[] =
{
  /* formato: { vnum, indirizzo }, */
  { 1, MageGuildMaster },   /* commento */
  {2,WarriorGuildMaster},
  // { 3, ThiefGuildMaster },
#if 0
  { 4, ClericGuildMaster },
#else
  { 5, DruidGuildMaster },
#endif
  { 6, Cityguard },
  { x, Rotta }, { 7 Rotta }, { 8, },
  { 1, ClericGuildMaster },
  { -1, NULL },
  { 9, MageGuildMaster }
};
static struct RoomSpecialProcEntry specials[] = { { 99, Donation }, { -1, NULL } };
"""


def test_parse_ignores_comments_if0_malformed_and_rooms() -> None:
    """Commenti, `#if 0`, righe malformate e tabella delle stanze ignorati; vnum doppio: l'ultimo; vnum negativo chiude."""
    assert parse_spec_assign(TABLE) == {1: "ClericGuildMaster", 2: "WarriorGuildMaster", 5: "DruidGuildMaster", 6: "Cityguard"}


def test_parse_edge_cases() -> None:
    """Senza tabella o vuoto: nessuna procedura; `#ifndef` e `#if` ignoti valgono come veri; `#elif` dopo `#if 0` e' attivo."""
    assert parse_spec_assign("") == {} and parse_spec_assign("int x;") == {}
    text = "struct special_proc_entry s[] = {\n#if 0\n{1,A},\n#elif FOO\n{2,B},\n#endif\n#ifndef X\n{3,C},\n#endif\n{-1,NULL}};"
    assert parse_spec_assign(text) == {2: "B", 3: "C"}


def test_read_missing_huge_binary(tmp_path: Path) -> None:
    """File mancante, enorme o binario: `SpecAssignError`; `SpecAssign` risponde `None` senza eccezioni."""
    with pytest.raises(SpecAssignError):
        read_spec_assign(tmp_path / "manca.c")
    huge = tmp_path / "huge.c"
    huge.write_bytes(b"x" * (MAX_BYTES + 1))
    binary = tmp_path / "bin.c"
    binary.write_bytes(b"\x00\x01\x02 special_proc_entry s[] = {{1,A}}")
    for bad in (huge, binary):
        with pytest.raises(SpecAssignError):
            read_spec_assign(bad)
        assert SpecAssign(bad).procs() is None and not SpecAssign(bad).supported and SpecAssign(bad).report().warnings
    assert SpecAssign(tmp_path / "manca.c").is_trainer(1) is None


def test_cache_follows_file_changes(tmp_path: Path) -> None:
    """La cache si invalida quando cambiano data o dimensione del file."""
    path = tmp_path / "spec_assign.c"
    path.write_text("struct special_proc_entry s[] = {{1,MageGuildMaster},{-1,NULL}};")
    spec = SpecAssign(path)
    assert spec.is_trainer(1) is True and spec.proc_of(1) == "MageGuildMaster"
    path.write_text("struct special_proc_entry s[] = {{1,Cityguard},{22,ThiefGuildMaster},{-1,NULL}};")
    assert spec.is_trainer(1) is False and spec.is_trainer(22) is True
    path.unlink()
    assert spec.is_trainer(22) is None


def test_locate_and_param_validation(tmp_path: Path) -> None:
    """Percorso dedotto dalla radice di `lib/`; `params.spec_assign` deve essere assoluto."""
    assert SpecAssign.locate(tmp_path / "lib", None).path == tmp_path / "src" / "spec_assign.c"
    assert SpecAssign.locate(tmp_path / "lib", str(tmp_path / "x.c")).path == tmp_path / "x.c"
    for bad in ("relativo.c", 5, ["/x"]):
        with pytest.raises(ValueError, match="spec_assign"):
            SpecAssign.locate(tmp_path / "lib", bad)


def _world(tmp_path: Path, **params: object) -> DikumodAdapter:
    """Adapter sul mondo sintetico (radice = `tmp_path`, `lib/` dentro)."""
    lib = write_dikumod_world(tmp_path / "lib")
    return DikumodAdapter(WorldConfig(id="syn", kind="dikumod", name="Sintetico", path=str(lib), params=params))


async def test_adapter_without_spec_assign_is_unchanged(tmp_path: Path) -> None:
    """Senza `src/spec_assign.c`: nessun errore, campo `isTrainer` non supportato, niente `extra.specProc`, filtro ignorato."""
    adapter = _world(tmp_path)
    mob = next(r for r in adapter.describe().resources if r.type == "mob")
    assert next(f for f in mob.fields if f.name == "isTrainer").unsupported
    assert "specProc" not in {f.name for f in mob.extra_fields}
    page = await adapter.list_mobs(MobPageParams(trainer=True))
    assert page.total == 3 and all(m.is_trainer is None and "specProc" not in m.extra for m in page.items)
    report = adapter.schema_report()
    assert report.count is None and report.warnings[0].code == "spec_assign_missing"


@pytest.mark.parametrize("explicit", [False, True])
async def test_adapter_with_spec_assign(tmp_path: Path, explicit: bool) -> None:
    """Con il file (dedotto o `params.spec_assign`): `extra.specProc`, `isTrainer` e filtro `trainer` coerenti."""
    src = tmp_path / ("altro.c" if explicit else "src/spec_assign.c")
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("struct special_proc_entry s[] = { {1, WarriorGuildMaster}, {2, Cityguard}, {-1, NULL} };")
    adapter = _world(tmp_path, **({"spec_assign": str(src)} if explicit else {}))
    mob = next(r for r in adapter.describe().resources if r.type == "mob")
    assert not next(f for f in mob.fields if f.name == "isTrainer").unsupported
    assert any(f.name == "specProc" and f.read_only for f in mob.extra_fields)
    by_vnum = {m.vnum: m for m in (await adapter.list_mobs(MobPageParams())).items}
    assert [by_vnum[v].is_trainer for v in (1, 2, 100)] == [True, False, False]
    assert [by_vnum[v].extra["specProc"] for v in (1, 2, 100)] == ["WarriorGuildMaster", "Cityguard", None]
    assert [m.vnum for m in (await adapter.list_mobs(MobPageParams(trainer=True))).items] == [1]
    assert [m.vnum for m in (await adapter.list_mobs(MobPageParams(trainer=False))).items] == [2, 100]
    assert adapter.schema_report().count == 2


async def test_spec_proc_is_read_only_in_patch(tmp_path: Path) -> None:
    """Rimandare `extra.specProc` in un PUT non da' errore e non scrive nulla (il file C non si tocca)."""
    from pachimudeditor.common.adapters.models import MobPatch

    src = tmp_path / "src" / "spec_assign.c"
    src.parent.mkdir()
    text = "struct special_proc_entry s[] = { {1, MageGuildMaster}, {-1, NULL} };"
    src.write_text(text)
    adapter = DikumodAdapter(
        WorldConfig(id="syn", kind="dikumod", name="S", path=str(write_dikumod_world(tmp_path / "lib")), read_only=False)
    )
    out = await adapter.update_mob(1, MobPatch(level=3, extra={"specProc": "Qualunque"}))
    assert out.level == 3 and out.extra["specProc"] == "MageGuildMaster" and src.read_text() == text


def test_teaching_procs_are_the_known_ones() -> None:
    """Le procedure che insegnano sono quelle che gestiscono practice/gain; gli sfidanti dei monaci no."""
    assert len(TEACHING_PROCS) == 11 and "monk_master" in TEACHING_PROCS and "MonkChallenger" not in TEACHING_PROCS


SPEC_REAL = Path(os.environ.get("DIKUMOD_SPEC_ASSIGN") or real_data.DIKUMOD_SRC / "src" / "spec_assign.c")


@pytest.mark.real_dikumod
async def test_real_leu_guildmasters(lib: Path) -> None:
    """Sui dati reali di leu (copia dei dati, `spec_assign.c` letto dall'originale): tutte le voci `*GuildMaster` sono maestri."""
    if not SPEC_REAL.is_file():
        pytest.skip(f"{SPEC_REAL} non trovato")
    text = SPEC_REAL.read_text(encoding="latin-1")
    pairs = re.findall(r"\{\s*(\d+)\s*,\s*(\w+)\s*\}", text)
    classic = {int(v) for v, name in pairs if name.lower().endswith("guildmaster")}
    wanted = classic | {int(v) for v, name in pairs if name == "monk_master"}
    assert len(classic) >= 26 and 691 in wanted  # le 26 voci *GuildMaster piu' gli altri maestri (Cain, il maestro dei monaci)
    adapter = DikumodAdapter(WorldConfig(id="dikumod", kind="dikumod", name="leu", path=str(lib), params={"spec_assign": str(SPEC_REAL)}))
    trainers = {m.vnum for m in (await adapter.list_mobs(MobPageParams(trainer=True, pageSize=100))).items}
    assert trainers == wanted and 691 in trainers
    others = (await adapter.list_mobs(MobPageParams(trainer=False, pageSize=5))).items
    assert others and all(m.is_trainer is False and m.vnum not in wanted for m in others)
    assert (await adapter.get_mob(30)).extra["specProc"] == "MageGuildMaster"


async def test_http_trainer_filter(client: httpx.AsyncClient, tmp_path: Path) -> None:
    """`GET /api/mobs?trainer=true` con `X-World` su un mondo con `spec_assign.c`, `isTrainer`/`extra.specProc` nel JSON."""
    lib = write_dikumod_world(tmp_path / "lib")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "spec_assign.c").write_text("struct special_proc_entry s[] = { {2, ThiefGuildMaster}, {-1, NULL} };")
    set_registry(
        WorldRegistry(
            [
                WorldConfig(id="pachimud", name="Pachimud", params=stack.current_params()),
                WorldConfig(id="dikumod", kind="dikumod", name="Diku Modificato", path=str(lib)),
            ]
        )
    )
    try:
        head = {"X-World": "dikumod"}
        page = data(await client.get("/api/mobs", params={"trainer": "true"}, headers=head))
        assert [m["vnum"] for m in page["items"]] == [2] and page["items"][0]["isTrainer"] is True
        assert page["items"][0]["extra"]["specProc"] == "ThiefGuildMaster"
        assert [m["vnum"] for m in data(await client.get("/api/mobs", params={"trainer": "false"}, headers=head))["items"]] == [1, 100]
    finally:
        await registry_module._registry.aclose_all()  # noqa: SLF001 - chiude gli engine prima della fine del loop
        set_registry(None)
