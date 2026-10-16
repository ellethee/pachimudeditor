"""Funzioni di supporto condivise dai router players: arricchimento righe, validazioni, cascade."""

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from pydantic import BaseModel
from sqlalchemy import Integer, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.definitions import read_classes, read_races
from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.sdk import conflict, not_found
from pachimudeditor.common.enums import Position

from .schemas import CharacterDetail, CharacterSummary, OptionOut, RefOut


def humanize(value: str) -> str:
    """`"POSITION_X"` -> `"Position x"`."""
    return value.replace("_", " ").capitalize()


def enum_options(enum_cls: type[Enum]) -> list[OptionOut]:
    """Opzioni `{value, label}` di un'enum intera."""
    return [OptionOut(value=int(m.value), label=humanize(m.name)) for m in enum_cls]  # type: ignore[call-overload]


def content_refs(definitions: Path | None) -> tuple[list[RefOut], list[RefOut]]:
    """Razze e classi correnti dagli YAML di `definitions/` del mondo (rilette a ogni chiamata)."""
    return (
        sorted((RefOut(id=r.race_id, name=r.name) for r in read_races(definitions).values()), key=lambda x: x.name),
        sorted((RefOut(id=c.class_id, name=c.name) for c in read_classes(definitions).values()), key=lambda x: x.name),
    )


def encode_position(session: AsyncSession, value: Position) -> str | int:
    """Il valore da scrivere in `player_character.position`: il gioco salva il NOME (colonna testuale), ma se la
    colonna fosse intera si scrive il numero."""
    column = models_of(session).PlayerCharacter.__table__.c.position  # type: ignore[union-attr]
    return int(value) if isinstance(column.type, Integer) else Position(value).name


async def ensure_account_exists(session: AsyncSession, account_id: int) -> None:
    """422 `players.invalid_account` se l'account non esiste."""
    if await session.get(models_of(session).Account, account_id) is None:
        raise api_error(422, "players.invalid_account", loc=("body", "accountId"), id=account_id)


async def ensure_room_exists(session: AsyncSession, room_id: int, field: str = "currentRoomId") -> None:
    """422 `players.invalid_room` se la stanza non esiste."""
    if await session.get(models_of(session).Room, room_id) is None:
        raise api_error(422, "players.invalid_room", loc=("body", field), id=room_id)


def ensure_class_race_valid(definitions: Path | None, class_id: str | None, race_id: str | None) -> None:
    """422 `players.invalid_class` / `players.invalid_race` se l'id non e' nelle definizioni YAML."""
    if class_id is None and race_id is None:
        return
    races, classes = content_refs(definitions)
    if class_id is not None and class_id not in {c.id for c in classes}:
        raise api_error(422, "players.invalid_class", loc=("body", "classId"), id=class_id)
    if race_id is not None and race_id not in {r.id for r in races}:
        raise api_error(422, "players.invalid_race", loc=("body", "raceId"), id=race_id)


async def ensure_character_name_free(session: AsyncSession, name: str, *, ignore_id: int | None = None) -> None:
    """409 `players.name_taken` se un altro personaggio usa gia' il nome."""
    PlayerCharacter = models_of(session).PlayerCharacter  # noqa: N806
    found = (await session.execute(select(PlayerCharacter).where(PlayerCharacter.name == name))).scalars().first()
    if found is not None and found.id != ignore_id:
        raise conflict("players.name_taken", name=name)


async def get_character_or_404(session: AsyncSession, character_id: int) -> Any:
    """Il personaggio o 404 `players.character_not_found`."""
    row = await session.get(models_of(session).PlayerCharacter, character_id)
    if row is None:
        raise not_found("players.character_not_found", id=character_id)
    return row


async def _context(session: AsyncSession, rows: Sequence[Any]) -> tuple[dict[int, str], dict[int, Any]]:
    """Username degli account e stanze referenziati dalle righe."""
    m = models_of(session)
    Account, Room = m.Account, m.Room  # noqa: N806
    account_ids = {r.account_id for r in rows}
    room_ids = {r.current_room_id for r in rows if r.current_room_id is not None}
    accounts: dict[int, str] = {}
    rooms: dict[int, Any] = {}
    if account_ids:
        res = await session.execute(select(Account.id, Account.username).where(Account.id.in_(account_ids)))
        accounts = {i: u for i, u in res.all()}
    if room_ids:
        res = await session.execute(select(Room).where(Room.id.in_(room_ids)))
        rooms = {r.id: r for r in res.scalars().all()}
    return accounts, rooms


async def to_summaries(session: AsyncSession, rows: Sequence[Any]) -> list[CharacterSummary]:
    """Righe di lista arricchite con username dell'account e vnum/nome della stanza."""
    accounts, rooms = await _context(session, rows)
    out: list[CharacterSummary] = []
    for row in rows:
        item = CharacterSummary.model_validate(row)
        item.account_username = accounts.get(row.account_id)
        room = rooms.get(row.current_room_id) if row.current_room_id is not None else None
        if room is not None:
            item.current_room_vnum, item.current_room_name = room.vnum, room.name
        out.append(item)
    return out


async def to_detail(session: AsyncSession, row: Any) -> CharacterDetail:
    """Scheda completa con contesto e numero di oggetti posseduti."""
    base = (await to_summaries(session, [row]))[0]
    detail = CharacterDetail.model_validate(row)
    detail.account_username = base.account_username
    detail.current_room_vnum = base.current_room_vnum
    detail.current_room_name = base.current_room_name
    detail.item_count = len(await collect_item_ids(session, row.id))
    return detail


async def collect_item_ids(session: AsyncSession, character_id: int) -> list[int]:
    """Id di tutte le istanze possedute: dirette e annidate in contenitori (risalita per livelli)."""
    ObjectInstance = models_of(session).ObjectInstance  # noqa: N806
    res = await session.execute(select(ObjectInstance.id).where(ObjectInstance.character_id == character_id))
    found = [i for (i,) in res.all()]
    frontier = list(found)
    while frontier:
        res = await session.execute(select(ObjectInstance.id).where(ObjectInstance.container_instance_id.in_(frontier)))
        frontier = [i for (i,) in res.all() if i not in found]
        found.extend(frontier)
    return found


async def delete_items(session: AsyncSession, item_ids: Sequence[int]) -> None:
    """Elimina le istanze indicate (senza commit)."""
    ObjectInstance = models_of(session).ObjectInstance  # noqa: N806
    if item_ids:
        await session.execute(delete(ObjectInstance).where(ObjectInstance.id.in_(list(item_ids))))


async def count_characters(session: AsyncSession, account_ids: Sequence[int]) -> dict[int, int]:
    """Numero di personaggi per account."""
    if not account_ids:
        return {}
    PlayerCharacter = models_of(session).PlayerCharacter  # noqa: N806
    res = await session.execute(
        select(PlayerCharacter.account_id, func.count())
        .where(PlayerCharacter.account_id.in_(list(account_ids)))
        .group_by(PlayerCharacter.account_id)
    )
    return {i: c for i, c in res.all()}


async def prototype_by(session: AsyncSession, *, prototype_id: int | None, vnum: int | None) -> Any:
    """Il prototipo per id o vnum; 422 se mancano entrambi, 404/422 se non esiste."""
    if prototype_id is None and vnum is None:
        raise api_error(422, "players.prototype_required", loc=("body", "prototypeId"))
    ObjectPrototype = models_of(session).ObjectPrototype  # noqa: N806
    stmt = select(ObjectPrototype)
    stmt = stmt.where(ObjectPrototype.id == prototype_id) if prototype_id is not None else stmt.where(ObjectPrototype.vnum == vnum)
    proto = (await session.execute(stmt)).scalars().first()
    if proto is None:
        raise api_error(422, "players.invalid_prototype", loc=("body", "prototypeId"))
    return proto


def dump(model: BaseModel) -> dict:
    """Valori Python (per nome) dei soli campi inviati."""
    return model.model_dump(exclude_unset=True, by_alias=False)
