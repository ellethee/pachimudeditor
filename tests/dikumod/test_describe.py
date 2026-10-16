"""`describe()` di Diku Modificato: le chiavi di `extra` dichiarate coincidono con quelle emesse sui dati reali (copia)."""

from pachimudeditor_adapter_dikumod.adapter import DikumodAdapter
from tests.support.describe_check import assert_describe_matches, emitted_extra_keys


async def test_extra_keys_match_emitted(ro: DikumodAdapter) -> None:
    """Zone, stanze, uscite, mob (anche corrotti), oggetti e reset: nessuna deriva tra descrittori e dati."""
    info = ro.describe()
    assert_describe_matches(info, await emitted_extra_keys(ro, rooms=500))
    enums = await ro.enums()
    for r in info.resources:
        for f in r.extra_fields:
            assert f.enum is None or f.enum in enums, (r.type, f.name, f.enum)
        for f in r.fields:
            assert f.enum is None or f.enum in enums, (r.type, f.name, f.enum)


def test_unsupported_and_derived_fields(ro: DikumodAdapter) -> None:
    """Campi senza equivalente `unsupported` + sola lettura; `bottomVnum` derivato; zone create in coda."""
    by = {r.type: {f.name: f for f in r.fields} for r in ro.describe().resources}
    zone = next(r for r in ro.describe().resources if r.type == "zone")
    assert zone.create_at_end and by["zone"]["bottomVnum"].read_only and not by["zone"]["bottomVnum"].unsupported
    assert by["zone"]["builder"].unsupported and by["room"]["healRate"].unsupported and by["mob"]["shopId"].unsupported
    assert not by["room"]["name"].unsupported and not by["object"]["rent"].unsupported
    mob = next(r for r in ro.describe().resources if r.type == "mob")
    assert {f.name: f.type for f in mob.extra_fields}["shop"] == "json"
    assert next(f for f in mob.extra_fields if f.name == "corrupted").group == "diagnostic"


def test_reset_condition_is_supported(ro: DikumodAdapter) -> None:
    """Diku Modificato ha `ifValue` e `comment` sui reset (basedmud/mapping no)."""
    reset = next(r for r in ro.describe().resources if r.type == "reset_command")
    by = {f.name: f for f in reset.fields}
    assert not by["ifValue"].unsupported and not by["comment"].unsupported
