"""`describe()` di BasedMud: le chiavi di `extra` dichiarate coincidono con quelle emesse sulle aree reali (copia)."""

from pachimudeditor_adapter_basedmud.adapter import BasedMudAdapter
from tests.support.describe_check import assert_describe_matches, emitted_extra_keys


async def test_extra_keys_match_emitted(adapter: BasedMudAdapter) -> None:
    """Zone, stanze, mob e oggetti: nessuna deriva tra descrittori e dati."""
    info = adapter.describe()
    assert_describe_matches(info, await emitted_extra_keys(adapter, rooms=300))
    enums = await adapter.enums()
    for r in info.resources:
        for f in (*r.extra_fields, *r.fields):
            assert f.enum is None or f.enum in enums, (r.type, f.name, f.enum)


def test_unsupported_fields(adapter: BasedMudAdapter) -> None:
    """I campi che ROM non ha sono `unsupported`."""
    by = {r.type: {f.name: f for f in r.fields} for r in adapter.describe().resources}
    assert (
        by["zone"]["resetMode"].unsupported
        and by["mob"]["experience"].unsupported
        and by["object"]["rent"].unsupported
        and by["reset_command"]["ifValue"].unsupported
    )
    assert not by["zone"]["name"].unsupported
