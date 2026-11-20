"""Funzioni di supporto condivise dai router players: arricchimento righe, validazioni, cascade."""

from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pachifast.i18n import api_error
from pydantic import BaseModel
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud.definitions import read_classes, read_races
from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor.sdk import conflict, not_found
from pachimudeditor.common.enums import Position

from .schemas import CharacterDetail, CharacterSummary, OptionOut, RefOut

if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.adapter import PachimudAdapter


def humanize(value: str) -> str:
    """`"POSITION_X"` -> `"Position x"`."""
    return value.replace("_", " ").capitalize()


def enum_options(enum_cls: type[Enum]) -> list[OptionOut]:
    """Opzioni `{value, label}` di un'enum intera."""
    return [OptionOut(value=int(m.value), label=humanize(m.name)) for m in enum_cls]  # type: ignore[call-overload]


def content_refs(definitions: "Path | tuple[Path, ...] | None") -> tuple[list[RefOut], list[RefOut]]:
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


def ensure_room_exists(adapter: "PachimudAdapter", room_id: int, field: str = "currentRoomId") -> int:
    """Il vnum della stanza (`id == vnum`); 422 `players.invalid_room` se non esiste nei file del mondo."""
    if adapter.sync().find("room", room_id) is None:
        raise api_error(422, "players.invalid_room", loc=("body", field), id=room_id)
    return room_id


def ensure_class_race_valid(definitions: "Path | tuple[Path, ...] | None", class_id: str | None, race_id: str | None) -> None:
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


async def _context(session: AsyncSession, rows: Sequence[Any]) -> dict[int, str]:
    """Username degli account referenziati dalle righe."""
    Account = models_of(session).Account  # noqa: N806
    account_ids = {r.account_id for r in rows}
    if not account_ids:
        return {}
    res = await session.execute(select(Account.id, Account.username).where(Account.id.in_(account_ids)))
    return {i: u for i, u in res.all()}


async def to_summaries(session: AsyncSession, rows: Sequence[Any], adapter: "PachimudAdapter") -> list[CharacterSummary]:
    """Righe di lista arricchite con username dell'account e vnum/nome della stanza (dai file del mondo)."""
    accounts = await _context(session, rows)
    store = adapter.sync()
    out: list[CharacterSummary] = []
    for row in rows:
        item = CharacterSummary.model_validate(row)
        item.account_username = accounts.get(row.account_id)
        room = store.find("room", row.current_room_vnum) if row.current_room_vnum is not None else None
        if room is not None:
            item.current_room_id, item.current_room_vnum, item.current_room_name = room.vnum, room.vnum, room.model.name
        elif row.current_room_vnum is not None:
            item.current_room_vnum = row.current_room_vnum  # la stanza non esiste piu': resta il vnum
        out.append(item)
    return out


async def to_detail(session: AsyncSession, row: Any, adapter: "PachimudAdapter") -> CharacterDetail:
    """Scheda completa con contesto e numero di oggetti posseduti."""
    base = (await to_summaries(session, [row], adapter))[0]
    detail = CharacterDetail.model_validate(row)
    detail.account_username = base.account_username
    detail.current_room_id = base.current_room_id
    detail.current_room_vnum = base.current_room_vnum
    detail.current_room_name = base.current_room_name
    detail.item_count = len(flatten_inventory(row.inventory))
    return detail


def flatten_inventory(inventory: Any) -> list[tuple[dict[str, Any], int | None]]:
    """Le voci dell'inventario JSON del personaggio in ordine di visita (padre prima dei figli): `(voce, indice del padre)`.
    L'`id` di una voce e' la sua posizione in questa lista."""
    out: list[tuple[dict[str, Any], int | None]] = []

    def visit(entries: Any, parent: int | None) -> None:
        """Scende nei `contents`."""
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            out.append((entry, parent))
            visit(entry.get("contents"), len(out) - 1)

    visit(inventory, None)
    return out


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


def prototype_by(adapter: "PachimudAdapter", *, prototype_id: int | None, vnum: int | None) -> Any:
    """L'oggetto prototipo per vnum (`prototypeId == vnum`); 422 se mancano entrambi o non esiste."""
    wanted = prototype_id if prototype_id is not None else vnum
    if wanted is None:
        raise api_error(422, "players.prototype_required", loc=("body", "prototypeId"))
    item = adapter.sync().find("object", wanted)
    if item is None:
        raise api_error(422, "players.invalid_prototype", loc=("body", "prototypeId"))
    return item


def dump(model: BaseModel) -> dict:
    """Valori Python (per nome) dei soli campi inviati."""
    return model.model_dump(exclude_unset=True, by_alias=False)
