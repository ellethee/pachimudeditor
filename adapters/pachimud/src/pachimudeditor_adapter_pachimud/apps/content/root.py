"""Contenuti del gioco in YAML: razze e classi (`definitions/races`, `definitions/classes`). Prefisso `/api/content`.

Il game server legge questi file una sola volta all'avvio: ogni modifica ha effetto al riavvio del server.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Path as PathParam
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from pachimudeditor_adapter_pachimud import race_enums
from pachimudeditor_adapter_pachimud.definitions import LoaderClass, LoaderRace, Stats
from pachimudeditor_adapter_pachimud.schema import models_of
from pachimudeditor_adapter_pachimud.apps.content.yaml_store import StoredFile, YamlDirStore
from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep, SessionDep

router = get_router(deps=[Depends(require_capability("supports_content_races"))])

STAT_NAMES: tuple[str, ...] = tuple(Stats.model_fields)
"""Nomi delle sei caratteristiche (`strength`, ...)."""

_FLAG_ENUMS: dict[str, Any] = {
    "mob_flags": race_enums.MobileFlags,
    "offensive_flags": race_enums.OffensiveFlags,
    "immunity": race_enums.ResistanceFlags,
    "resistance": race_enums.ResistanceFlags,
    "vulnerability": race_enums.ResistanceFlags,
    "form": race_enums.FormFlags,
    "actual_form": race_enums.FormFlags,
    "parts": race_enums.PartFlags,
    "affected_by": race_enums.AffectedByFlags,
}
"""Per ogni campo-lista di flag di una razza, l'enum dei nomi ammessi."""


def _flag_names(enum_cls: Any) -> list[str]:
    """I nomi dei membri 'singoli' di un IntFlag (esclusi gli alias composti e quelli senza bit)."""
    return [m.name for m in enum_cls if m.name and bin(m.value).count("1") == 1]


def _definitions_root(adapter: PachimudDep) -> Path:
    """La cartella `definitions` del mondo attivo (`params.definitions_path`; 409 se il mondo non la configura)."""
    root = adapter.params.definitions_path
    if root is None:
        raise api_error(409, "world.capability_missing", capability="supports_content_races")
    return root


def _validate_race(raw: Mapping[str, Any]) -> list[str]:
    """Regole extra per una razza: nomi di flag e taglia esistenti (il game server ignora in silenzio i refusi)."""
    problems: list[str] = []
    for field, enum_cls in _FLAG_ENUMS.items():
        valid = {name.upper() for name in enum_cls.__members__}
        for value in raw.get(field) or []:
            if str(value).upper() not in valid:
                problems.append(f"{field}: flag sconosciuto {value!r}")
    size = raw.get("size")
    if size is not None and str(size) not in race_enums.SizeType.__members__:
        problems.append(f"size: valore sconosciuto {size!r}")
    return problems


def _validate_class(raw: Mapping[str, Any]) -> list[str]:
    """Regole extra per una classe: caratteristiche esistenti in `attrs_priority`/`attr_prime`."""
    problems = [f"attrs_priority: caratteristica sconosciuta {v!r}" for v in raw.get("attrs_priority") or [] if v not in STAT_NAMES]
    prime = raw.get("attr_prime")
    if prime not in (None, "") and prime not in STAT_NAMES:
        problems.append(f"attr_prime: caratteristica sconosciuta {prime!r}")
    if len(set(raw.get("attrs_priority") or [])) != len(raw.get("attrs_priority") or []):
        problems.append("attrs_priority: caratteristiche duplicate")
    return problems


def _races_store(adapter: PachimudDep) -> YamlDirStore:
    """Lo store delle razze del mondo attivo."""
    return YamlDirStore(lambda: _definitions_root(adapter), "races", LoaderRace, "race_id", validate=_validate_race)


def _classes_store(adapter: PachimudDep) -> YamlDirStore:
    """Lo store delle classi del mondo attivo."""
    return YamlDirStore(lambda: _definitions_root(adapter), "classes", LoaderClass, "class_id", validate=_validate_class)


RacesDep = Annotated[YamlDirStore, Depends(_races_store)]
"""Lo store delle razze del mondo pachimud attivo (cartella `definitions/races`)."""
ClassesDep = Annotated[YamlDirStore, Depends(_classes_store)]
"""Lo store delle classi del mondo pachimud attivo (cartella `definitions/classes`)."""


class RaceBody(AliasedBaseModel, LoaderRace):
    """Corpo di creazione/modifica di una razza: stessi campi del file YAML (camelCase sul filo).
    In PUT vengono applicati solo i campi effettivamente inviati."""


class ClassBody(AliasedBaseModel, LoaderClass):
    """Corpo di creazione/modifica di una classe: stessi campi del file YAML (camelCase sul filo)."""


class RaceItem(RaceBody):
    """Una razza come restituita dall'API: campi del file + metadati."""

    file: str
    disabled: bool = False
    """`True` se il file e' stato disattivato per rinomina (`.yaml.disabled`)."""
    mob_count: int = 0
    """Quanti prototipi di mob usano questa razza (`race_id`)."""
    valid: bool = True
    error: str | None = None


class ClassItem(ClassBody):
    """Una classe come restituita dall'API: campi del file + metadati.

    `disabled` e' vero se il file e' stato disattivato per rinomina (`.yaml.disabled`) oppure contiene
    `disabled: true`. Nota: `BaseClass.load_from_yaml` del gioco oggi non copia il flag `disabled`,
    quindi l'unico meccanismo effettivo e' la rinomina."""

    file: str
    mob_count: int = 0
    """Quanti prototipi di mob la usano (`class_id`) o la insegnano (`teaches_class_ids`)."""
    valid: bool = True
    error: str | None = None


class EnumOption(AliasedBaseModel):
    """Una voce di select."""

    value: str
    label: str


class ContentOptions(AliasedBaseModel):
    """Valori ammessi per i campi dei form di razze e classi."""

    mob_flags: list[str]
    offensive_flags: list[str]
    resistance_flags: list[str]
    form_flags: list[str]
    part_flags: list[str]
    affected_by_flags: list[str]
    sizes: list[str]
    stats: list[str]


class ContentStatus(AliasedBaseModel):
    """Stato dei contenuti, per il banner 'riavvio necessario'."""

    races: int
    classes: int
    last_modified: float | None
    """Timestamp (secondi epoch) dell'ultima modifica di un file di razze/classi."""


IdParam = Annotated[str, PathParam(pattern=r"^[a-z0-9][a-z0-9_]{0,63}$")]


async def _race_usage(session: AsyncSession) -> dict[str, int]:
    """`race_id -> numero di mob` (una sola query)."""
    MobPrototype = models_of(session).MobPrototype  # noqa: N806
    if "race_id" not in MobPrototype.__table__.c:
        return {}
    rows = await session.execute(
        select(MobPrototype.race_id, func.count()).where(MobPrototype.race_id.is_not(None)).group_by(MobPrototype.race_id)
    )
    return {race_id: count for race_id, count in rows}


async def _class_usage(session: AsyncSession) -> dict[str, int]:
    """`class_id -> numero di mob` che la usano (`class_id`) o la insegnano (`teaches_class_ids`)."""
    usage: dict[str, int] = {}
    MobPrototype = models_of(session).MobPrototype  # noqa: N806
    table = MobPrototype.__table__.c
    class_col = MobPrototype.class_id if "class_id" in table else literal(None)
    rows = await session.execute(select(class_col, MobPrototype.teaches_class_ids))
    for class_id, teaches in rows:
        ids = set(teaches or [])
        if class_id:
            ids.add(class_id)
        for value in ids:
            usage[value] = usage.get(value, 0) + 1
    return usage


def _race_item(store: YamlDirStore, stored: StoredFile, usage: Mapping[str, int]) -> RaceItem:
    """Costruisce l'item di una razza; un file non valido diventa un item con `valid=False` ed `error`."""
    stem = YamlDirStore.stem(stored.path)
    try:
        item = store.parse(stored.raw)
        assert isinstance(item, LoaderRace)
        race_id = item.race_id
        return RaceItem(**item.model_dump(), file=stored.path.name, disabled=stored.renamed_disabled, mob_count=usage.get(race_id, 0))
    except Exception as error:
        detail = getattr(error, "detail", None)
        message = detail[0].get("params", {}).get("detail") if isinstance(detail, list) and detail else str(error)
        return RaceItem(
            race_id=stem,
            name=stem,
            description="",
            file=stored.path.name,
            disabled=stored.renamed_disabled,
            valid=False,
            error=message or str(error),
        )


def _class_item(store: YamlDirStore, stored: StoredFile, usage: Mapping[str, int]) -> ClassItem:
    """Costruisce l'item di una classe (vedi `_race_item`)."""
    stem = YamlDirStore.stem(stored.path)
    try:
        item = store.parse(stored.raw)
        assert isinstance(item, LoaderClass)
        values = item.model_dump() | {"disabled": bool(item.disabled) or stored.renamed_disabled}
        return ClassItem(**values, file=stored.path.name, mob_count=usage.get(item.class_id, 0))
    except Exception as error:
        detail = getattr(error, "detail", None)
        message = detail[0].get("params", {}).get("detail") if isinstance(detail, list) and detail else str(error)
        return ClassItem(class_id=stem, name=stem, file=stored.path.name, valid=False, error=message or str(error))


def _payload(body: AliasedBaseModel) -> dict[str, Any]:
    """Solo i campi inviati dal client, con le chiavi snake_case del file YAML."""
    return body.model_dump(exclude_unset=True, by_alias=False)


# --- opzioni e stato -------------------------------------------------------------------------


@router.get("/options", response_model=ContentOptions)
async def options() -> ContentOptions:
    """Valori ammessi per le select dei form (flag, taglie, caratteristiche)."""
    return ContentOptions(
        mob_flags=_flag_names(race_enums.MobileFlags),
        offensive_flags=_flag_names(race_enums.OffensiveFlags),
        resistance_flags=_flag_names(race_enums.ResistanceFlags),
        form_flags=_flag_names(race_enums.FormFlags),
        part_flags=_flag_names(race_enums.PartFlags),
        affected_by_flags=_flag_names(race_enums.AffectedByFlags),
        sizes=[m.name for m in race_enums.SizeType],
        stats=list(STAT_NAMES),
    )


@router.get("/status", response_model=ContentStatus)
async def status(races_store: RacesDep, classes_store: ClassesDep) -> ContentStatus:
    """Numero di file e data dell'ultima modifica, per ricordare che serve il riavvio del game server."""
    files = [s.path for store in (races_store, classes_store) for s in store.stored()]
    mtimes = [p.stat().st_mtime for p in files]
    return ContentStatus(
        races=len(races_store.stored()), classes=len(classes_store.stored()), last_modified=max(mtimes) if mtimes else None
    )


# --- razze -----------------------------------------------------------------------------------


@router.get("/races", response_model=list[RaceItem])
async def list_races(session: SessionDep, races_store: RacesDep) -> list[RaceItem]:
    """Tutte le razze (anche disattivate o non valide), ordinate per nome."""
    usage = await _race_usage(session)
    return sorted((_race_item(races_store, s, usage) for s in races_store.stored()), key=lambda i: (i.name.lower(), i.race_id))


@router.post("/races", response_model=RaceItem, status_code=201)
async def create_race(body: RaceBody, session: SessionDep, races_store: RacesDep) -> RaceItem:
    """Crea `races/<raceId>.yaml`. 409 `content.id_taken`, 422 `content.invalid_id|invalid`."""
    return _race_item(races_store, races_store.create(_payload(body)), await _race_usage(session))


@router.get("/races/{item_id}", response_model=RaceItem)
async def get_race(item_id: IdParam, session: SessionDep, races_store: RacesDep) -> RaceItem:
    """Una razza. 404 `content.not_found`."""
    stored = races_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    return _race_item(races_store, stored, await _race_usage(session))


@router.put("/races/{item_id}", response_model=RaceItem)
async def update_race(item_id: IdParam, body: RaceBody, session: SessionDep, races_store: RacesDep) -> RaceItem:
    """Aggiorna i campi inviati, preservando commenti e formato. L'id non e' modificabile (422 `content.id_mismatch`)."""
    if body.race_id != item_id:
        raise api_error(422, "content.id_mismatch", id=item_id, body_id=body.race_id)
    return _race_item(races_store, races_store.update(item_id, _payload(body)), await _race_usage(session))


@router.post("/races/{item_id}/disable", response_model=RaceItem)
async def disable_race(item_id: IdParam, session: SessionDep, races_store: RacesDep) -> RaceItem:
    """Disattiva la razza rinominando il file in `.yaml.disabled` (il game server non lo carica piu')."""
    return _race_item(races_store, races_store.set_disabled(item_id, True), await _race_usage(session))


@router.post("/races/{item_id}/enable", response_model=RaceItem)
async def enable_race(item_id: IdParam, session: SessionDep, races_store: RacesDep) -> RaceItem:
    """Riattiva una razza disattivata."""
    return _race_item(races_store, races_store.set_disabled(item_id, False), await _race_usage(session))


@router.delete("/races/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_race(item_id: IdParam, session: SessionDep, races_store: RacesDep) -> None:
    """Elimina il file. 409 `content.race_in_use` (con `count`) se dei mob usano la razza."""
    stored = races_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    count = (await _race_usage(session)).get(item_id, 0)
    if count:
        raise api_error(409, "content.race_in_use", id=item_id, count=count)
    races_store.delete(item_id)


# --- classi ----------------------------------------------------------------------------------


@router.get("/classes", response_model=list[ClassItem])
async def list_classes(session: SessionDep, classes_store: ClassesDep) -> list[ClassItem]:
    """Tutte le classi (anche disabilitate o non valide), ordinate per nome."""
    usage = await _class_usage(session)
    return sorted((_class_item(classes_store, s, usage) for s in classes_store.stored()), key=lambda i: (i.name.lower(), i.class_id))


@router.post("/classes", response_model=ClassItem, status_code=201)
async def create_class(body: ClassBody, session: SessionDep, classes_store: ClassesDep) -> ClassItem:
    """Crea `classes/<classId>.yaml`. 409 `content.id_taken`, 422 `content.invalid_id|invalid`."""
    return _class_item(classes_store, classes_store.create(_payload(body)), await _class_usage(session))


@router.get("/classes/{item_id}", response_model=ClassItem)
async def get_class(item_id: IdParam, session: SessionDep, classes_store: ClassesDep) -> ClassItem:
    """Una classe. 404 `content.not_found`."""
    stored = classes_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    return _class_item(classes_store, stored, await _class_usage(session))


@router.put("/classes/{item_id}", response_model=ClassItem)
async def update_class(item_id: IdParam, body: ClassBody, session: SessionDep, classes_store: ClassesDep) -> ClassItem:
    """Aggiorna i campi inviati, preservando commenti e formato. L'id non e' modificabile."""
    if body.class_id != item_id:
        raise api_error(422, "content.id_mismatch", id=item_id, body_id=body.class_id)
    return _class_item(classes_store, classes_store.update(item_id, _payload(body)), await _class_usage(session))


@router.post("/classes/{item_id}/disable", response_model=ClassItem)
async def disable_class(item_id: IdParam, session: SessionDep, classes_store: ClassesDep) -> ClassItem:
    """Disattiva la classe rinominando il file in `.yaml.disabled` (il `ClassManager` non lo carica piu')."""
    return _class_item(classes_store, classes_store.set_disabled(item_id, True), await _class_usage(session))


@router.post("/classes/{item_id}/enable", response_model=ClassItem)
async def enable_class(item_id: IdParam, session: SessionDep, classes_store: ClassesDep) -> ClassItem:
    """Riattiva una classe disattivata."""
    return _class_item(classes_store, classes_store.set_disabled(item_id, False), await _class_usage(session))


@router.delete("/classes/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_class(item_id: IdParam, session: SessionDep, classes_store: ClassesDep) -> None:
    """Elimina il file. 409 `content.class_in_use` (con `count`) se dei mob la usano o la insegnano."""
    stored = classes_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    count = (await _class_usage(session)).get(item_id, 0)
    if count:
        raise api_error(409, "content.class_in_use", id=item_id, count=count)
    classes_store.delete(item_id)
