"""Conteggio delle istanze vive (mob, oggetti, personaggi) che dipendono da un prototipo o da una stanza.

Le FK da `mob_instance`/`object_instance`/`player_character` verso prototipi e stanze farebbero fallire
la delete con un 409 generico; qui si contano prima per rispondere con un codice dedicato e i numeri.
Le tabelle assenti dal DB (schema piu' vecchio/ridotto) contano come zero istanze.
"""

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.sdk import conflict


async def _count(session: AsyncSession, stmt: Select) -> int:
    """Esegue una `select(count())` e restituisce il numero."""
    return (await session.execute(stmt)).scalar_one()


async def ensure_mob_has_no_instances(session: AsyncSession, prototype_id: int) -> None:
    """409 `mobs.has_instances` (param `count`) se esistono istanze del mob."""
    MobInstance = models_of(session).MobInstance  # noqa: N806
    if MobInstance is None:
        return
    count = await _count(session, select(func.count()).select_from(MobInstance).where(MobInstance.prototype_id == prototype_id))
    if count:
        raise conflict("mobs.has_instances", count=count)


async def ensure_object_has_no_instances(session: AsyncSession, prototype_id: int) -> None:
    """409 `objects.has_instances` (param `count`) se esistono istanze dell'oggetto."""
    ObjectInstance = models_of(session).ObjectInstance  # noqa: N806
    if ObjectInstance is None:
        return
    count = await _count(session, select(func.count()).select_from(ObjectInstance).where(ObjectInstance.prototype_id == prototype_id))
    if count:
        raise conflict("objects.has_instances", count=count)


async def ensure_room_has_no_occupants(session: AsyncSession, room_id: int) -> None:
    """409 `rooms.has_instances` (params `mobs`, `objects`, `players`) se la stanza contiene istanze vive
    o e' l'ultima stanza nota di un personaggio."""
    m = models_of(session)
    mobs = objects = players = 0
    if m.MobInstance is not None:
        mobs = await _count(session, select(func.count()).select_from(m.MobInstance).where(m.MobInstance.room_id == room_id))
    if m.ObjectInstance is not None:
        objects = await _count(session, select(func.count()).select_from(m.ObjectInstance).where(m.ObjectInstance.room_id == room_id))
    if m.PlayerCharacter is not None:
        players = await _count(
            session,
            select(func.count()).select_from(m.PlayerCharacter).where(m.PlayerCharacter.current_room_id == room_id),
        )
    if mobs or objects or players:
        raise conflict("rooms.has_instances", mobs=mobs, objects=objects, players=players)
