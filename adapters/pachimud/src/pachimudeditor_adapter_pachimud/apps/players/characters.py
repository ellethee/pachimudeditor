"""Personaggi giocanti: lista/filtri, scheda, modifica con validazione FK, teletrasporto, eliminazione."""

from typing import Annotated

from fastapi import Query
from pachifast.database.pagination import paginate
from pachifast.router_factory import get_router
from pachifast.schemas.responses import PageParams, PaginatedResponse

from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.editor import crud
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep, SessionDep
from pachimudeditor.sdk import conflict
from pachimudeditor_adapter_pachimud.editor.pagination import default_order
from pachimudeditor.common.enums import Position, Sex

from .helpers import (
    collect_item_ids,
    content_refs,
    delete_items,
    ensure_account_exists,
    ensure_character_name_free,
    ensure_class_race_valid,
    ensure_room_exists,
    encode_position,
    enum_options,
    get_character_or_404,
    to_detail,
    to_summaries,
)
from .schemas import CharacterDetail, CharacterPatch, CharacterSummary, LookupsOut, TeleportIn

router = get_router(prefix="")


class CharacterPageParams(PageParams):
    """Lista personaggi: `search` su nome/titolo/classe/razza; filtri esatti `accountId`, `classId`, `raceId`,
    `currentRoomId`."""

    search_fields = ["name", "title", "class_id", "race_id"]
    order_fields = ["id", "name", "level", "account_id", "created_at", "last_played_at", "gold"]
    account_id: int | None = Query(None)
    class_id: str | None = Query(None)
    race_id: str | None = Query(None)
    current_room_id: int | None = Query(None)


@router.get("/lookups", response_model=LookupsOut)
async def lookups(adapter: PachimudDep) -> LookupsOut:
    """Opzioni per i form: sesso, posizione, razze e classi valide (rilette dagli YAML)."""
    races, classes = content_refs(adapter.params.definitions_path)
    return LookupsOut(sex=enum_options(Sex), position=enum_options(Position), races=races, classes=classes)


@router.get("/characters", response_model=PaginatedResponse[CharacterSummary])
async def list_characters(params: Annotated[CharacterPageParams, Query()], session: SessionDep) -> PaginatedResponse[CharacterSummary]:
    """Personaggi paginati, filtrabili per account/classe/razza/stanza; ordine di default per nome."""
    page = await paginate(session, models_of(session).PlayerCharacter, params, extra_filters=[default_order("name")])
    page.items = await to_summaries(session, page.items)
    return page


@router.get("/characters/{character_id}", response_model=CharacterDetail)
async def get_character(character_id: int, session: SessionDep) -> CharacterDetail:
    """Scheda completa di un personaggio."""
    return await to_detail(session, await get_character_or_404(session, character_id))


@router.put("/characters/{character_id}", response_model=CharacterDetail)
async def update_character(character_id: int, data: CharacterPatch, session: SessionDep, adapter: PachimudDep) -> CharacterDetail:
    """Aggiornamento parziale. Valida account, stanza (id), classe/razza (definizioni YAML) e unicita' del nome."""
    await get_character_or_404(session, character_id)
    fields = data.model_fields_set
    if "account_id" in fields:
        await ensure_account_exists(session, data.account_id)  # type: ignore[arg-type]
    if data.current_room_id is not None:
        await ensure_room_exists(session, data.current_room_id)
    ensure_class_race_valid(adapter.params.definitions_path, data.class_id, data.race_id)
    if data.name is not None:
        await ensure_character_name_free(session, data.name, ignore_id=character_id)
    values = data.model_dump(exclude_unset=True, by_alias=False)
    if values.get("position") is not None:
        values["position"] = encode_position(session, values["position"])
    updated = await crud.update(session, models_of(session).PlayerCharacter, character_id, values, code="players.character_not_found")
    return await to_detail(session, updated)


@router.post("/characters/{character_id}/teleport", response_model=CharacterDetail)
async def teleport_character(character_id: int, data: TeleportIn, session: SessionDep) -> CharacterDetail:
    """Sposta il personaggio nella stanza `roomId` (422 `players.invalid_room` se non esiste)."""
    await get_character_or_404(session, character_id)
    await ensure_room_exists(session, data.room_id, "roomId")
    updated = await crud.update(
        session,
        models_of(session).PlayerCharacter,
        character_id,
        {"current_room_id": data.room_id},
        code="players.character_not_found",
    )
    return await to_detail(session, updated)


@router.delete("/characters/{character_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_character(character_id: int, session: SessionDep, cascade: bool = Query(False)) -> None:
    """Elimina il personaggio. Con oggetti: 409 `players.character_has_items`, salvo `?cascade=true`
    che elimina anche l'inventario."""
    character = await get_character_or_404(session, character_id)
    item_ids = await collect_item_ids(session, character_id)
    if item_ids and not cascade:
        raise conflict("players.character_has_items", count=len(item_ids))
    await delete_items(session, item_ids)
    await session.delete(character)
    await session.commit()
