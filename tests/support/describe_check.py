"""Verifica che le chiavi di `extra` dichiarate da `describe()` coincidano con quelle che l'adapter emette davvero."""

from pachimudeditor.common.adapters.base import AdapterInfo, WorldAdapter
from pachimudeditor.common.adapters.models import MobPageParams, ObjectPageParams, RoomPageParams, ZonePageParams

CONDITIONAL = frozenset({"corrupted", "warning", "line", "raw", "missingArg4"})
"""Chiavi emesse solo quando c'e' il problema (diagnostica): possono mancare nei dati campione."""


async def emitted_extra_keys(adapter: WorldAdapter, *, rooms: int = 400) -> dict[str, set[str]]:
    """Unione delle chiavi di `extra` lette dai dati, per risorsa (zone/room/exit/mob/object/reset_command)."""
    out: dict[str, set[str]] = {k: set() for k in ("zone", "room", "exit", "mob", "object", "reset_command")}
    zones = (await adapter.list_zones(ZonePageParams(page=1, pageSize=500))).items
    for z in zones:
        out["zone"] |= set(z.extra)
        if adapter.capabilities().supports_reset_scripts:
            for cmd in await adapter.list_reset_commands(z.id):
                out["reset_command"] |= set(cmd.extra)
    room_items = (await adapter.list_rooms(RoomPageParams(page=1, pageSize=rooms))).items
    for r in room_items:
        out["room"] |= set(r.extra)
        for ex in (await adapter.get_room(r.id)).exits:
            out["exit"] |= set(ex.extra)
    for m in (await adapter.list_mobs(MobPageParams(page=1, pageSize=5000))).items:
        out["mob"] |= set(m.extra)
    for o in (await adapter.list_objects(ObjectPageParams(page=1, pageSize=5000))).items:
        out["object"] |= set(o.extra)
    return out


def assert_describe_matches(
    info: AdapterInfo, emitted: dict[str, set[str]], *, conditional: frozenset[str] = CONDITIONAL, optional: bool = False
) -> None:
    """Ogni chiave emessa e' dichiarata; ogni chiave dichiarata e' emessa (salvo la diagnostica condizionale).

    `optional`: mappatura generica, dove un campo del record compare in `extra` solo se il record lo ha."""
    declared = {r.type: {f.name for f in r.extra_fields} for r in info.resources}
    for resource, keys in emitted.items():
        have = declared.get(resource, set())
        assert keys <= have, f"{resource}: chiavi emesse ma non dichiarate {sorted(keys - have)}"
        assert optional or have - keys <= conditional, f"{resource}: chiavi dichiarate ma mai emesse {sorted(have - keys - conditional)}"
    for r in info.resources:
        for f in r.extra_fields:
            assert f.label_key == f"extra.labels.{f.name}"
