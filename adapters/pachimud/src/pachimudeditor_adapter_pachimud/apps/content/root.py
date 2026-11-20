"""Contenuti del gioco in YAML: razze e classi (`definitions/races`, `definitions/classes`), skill, tabelle, social, cataloghi dei messaggi
e testi lunghi (`files_store.py`). Prefisso `/api/content`.

Il game server legge questi file all'avvio: ogni modifica ha effetto al riavvio, oppure subito con `content.reload` di livectl
(`POST /api/world/live/content/reload`), se il canale live e' configurato.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Path as PathParam
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.router_factory import get_router

from pachimudeditor_adapter_pachimud import race_enums
from pachimudeditor_adapter_pachimud.definitions import LoaderClass, LoaderRace, Stats
from pachimudeditor_adapter_pachimud.apps.content import files_store
from pachimudeditor_adapter_pachimud.apps.content.files_store import Layers
from pachimudeditor_adapter_pachimud.apps.content.yaml_store import StoredFile, YamlDirStore
from pachimudeditor.sdk import require_capability
from pachimudeditor_adapter_pachimud.editor.db import PachimudDep, ReadOnlyGuard

router = get_router(deps=[Depends(require_capability("supports_content_races")), ReadOnlyGuard])

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


async def _race_usage(adapter: PachimudDep) -> dict[str, int]:
    """`race_id -> numero di mob` (dai file YAML delle zone)."""
    usage: dict[str, int] = {}
    for mob in adapter.sync().all_items("mob"):
        if mob.model.race_id:
            usage[mob.model.race_id] = usage.get(mob.model.race_id, 0) + 1
    return usage


async def _class_usage(adapter: PachimudDep) -> dict[str, int]:
    """`class_id -> numero di mob` che la usano (`class_id`) o la insegnano (`teaches_class_ids`)."""
    usage: dict[str, int] = {}
    for mob in adapter.sync().all_items("mob"):
        ids = set(mob.model.teaches_class_ids or [])
        if mob.model.class_id:
            ids.add(mob.model.class_id)
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
async def list_races(adapter: PachimudDep, races_store: RacesDep) -> list[RaceItem]:
    """Tutte le razze (anche disattivate o non valide), ordinate per nome."""
    usage = await _race_usage(adapter)
    return sorted((_race_item(races_store, s, usage) for s in races_store.stored()), key=lambda i: (i.name.lower(), i.race_id))


@router.post("/races", response_model=RaceItem, status_code=201)
async def create_race(body: RaceBody, adapter: PachimudDep, races_store: RacesDep) -> RaceItem:
    """Crea `races/<raceId>.yaml`. 409 `content.id_taken`, 422 `content.invalid_id|invalid`."""
    return _race_item(races_store, races_store.create(_payload(body)), await _race_usage(adapter))


@router.get("/races/{item_id}", response_model=RaceItem)
async def get_race(item_id: IdParam, adapter: PachimudDep, races_store: RacesDep) -> RaceItem:
    """Una razza. 404 `content.not_found`."""
    stored = races_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    return _race_item(races_store, stored, await _race_usage(adapter))


@router.put("/races/{item_id}", response_model=RaceItem)
async def update_race(item_id: IdParam, body: RaceBody, adapter: PachimudDep, races_store: RacesDep) -> RaceItem:
    """Aggiorna i campi inviati, preservando commenti e formato. L'id non e' modificabile (422 `content.id_mismatch`)."""
    if body.race_id != item_id:
        raise api_error(422, "content.id_mismatch", id=item_id, body_id=body.race_id)
    return _race_item(races_store, races_store.update(item_id, _payload(body)), await _race_usage(adapter))


@router.post("/races/{item_id}/disable", response_model=RaceItem)
async def disable_race(item_id: IdParam, adapter: PachimudDep, races_store: RacesDep) -> RaceItem:
    """Disattiva la razza rinominando il file in `.yaml.disabled` (il game server non lo carica piu')."""
    return _race_item(races_store, races_store.set_disabled(item_id, True), await _race_usage(adapter))


@router.post("/races/{item_id}/enable", response_model=RaceItem)
async def enable_race(item_id: IdParam, adapter: PachimudDep, races_store: RacesDep) -> RaceItem:
    """Riattiva una razza disattivata."""
    return _race_item(races_store, races_store.set_disabled(item_id, False), await _race_usage(adapter))


@router.delete("/races/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_race(item_id: IdParam, adapter: PachimudDep, races_store: RacesDep) -> None:
    """Elimina il file. 409 `content.race_in_use` (con `count`) se dei mob usano la razza."""
    stored = races_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    count = (await _race_usage(adapter)).get(item_id, 0)
    if count:
        raise api_error(409, "content.race_in_use", id=item_id, count=count)
    races_store.delete(item_id)


# --- classi ----------------------------------------------------------------------------------


@router.get("/classes", response_model=list[ClassItem])
async def list_classes(adapter: PachimudDep, classes_store: ClassesDep) -> list[ClassItem]:
    """Tutte le classi (anche disabilitate o non valide), ordinate per nome."""
    usage = await _class_usage(adapter)
    return sorted((_class_item(classes_store, s, usage) for s in classes_store.stored()), key=lambda i: (i.name.lower(), i.class_id))


@router.post("/classes", response_model=ClassItem, status_code=201)
async def create_class(body: ClassBody, adapter: PachimudDep, classes_store: ClassesDep) -> ClassItem:
    """Crea `classes/<classId>.yaml`. 409 `content.id_taken`, 422 `content.invalid_id|invalid`."""
    return _class_item(classes_store, classes_store.create(_payload(body)), await _class_usage(adapter))


@router.get("/classes/{item_id}", response_model=ClassItem)
async def get_class(item_id: IdParam, adapter: PachimudDep, classes_store: ClassesDep) -> ClassItem:
    """Una classe. 404 `content.not_found`."""
    stored = classes_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    return _class_item(classes_store, stored, await _class_usage(adapter))


@router.put("/classes/{item_id}", response_model=ClassItem)
async def update_class(item_id: IdParam, body: ClassBody, adapter: PachimudDep, classes_store: ClassesDep) -> ClassItem:
    """Aggiorna i campi inviati, preservando commenti e formato. L'id non e' modificabile."""
    if body.class_id != item_id:
        raise api_error(422, "content.id_mismatch", id=item_id, body_id=body.class_id)
    return _class_item(classes_store, classes_store.update(item_id, _payload(body)), await _class_usage(adapter))


@router.post("/classes/{item_id}/disable", response_model=ClassItem)
async def disable_class(item_id: IdParam, adapter: PachimudDep, classes_store: ClassesDep) -> ClassItem:
    """Disattiva la classe rinominando il file in `.yaml.disabled` (il `ClassManager` non lo carica piu')."""
    return _class_item(classes_store, classes_store.set_disabled(item_id, True), await _class_usage(adapter))


@router.post("/classes/{item_id}/enable", response_model=ClassItem)
async def enable_class(item_id: IdParam, adapter: PachimudDep, classes_store: ClassesDep) -> ClassItem:
    """Riattiva una classe disattivata."""
    return _class_item(classes_store, classes_store.set_disabled(item_id, False), await _class_usage(adapter))


@router.delete("/classes/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_class(item_id: IdParam, adapter: PachimudDep, classes_store: ClassesDep) -> None:
    """Elimina il file. 409 `content.class_in_use` (con `count`) se dei mob la usano o la insegnano."""
    stored = classes_store.locate(item_id)
    if stored is None:
        raise api_error(404, "content.not_found", id=item_id)
    count = (await _class_usage(adapter)).get(item_id, 0)
    if count:
        raise api_error(409, "content.class_in_use", id=item_id, count=count)
    classes_store.delete(item_id)


# --- file a strati: skill, tabelle, social, cataloghi, testi -------------------------------------------------------------------


def _layers(adapter: PachimudDep) -> Layers:
    """Gli strati di contenuti del mondo attivo (base del gioco, poi `definitions_path`)."""
    return Layers(tuple(adapter.params.layers))


AreaParam = Annotated[str, PathParam(pattern=r"^(tables|locales|texts)$")]
FilePath = Annotated[str, PathParam(description="percorso relativo dentro l'area, es. `it/commands/social.yaml`")]


class FileEntry(AliasedBaseModel):
    """Un file di contenuti: percorso relativo all'area, strato (`user` = modificato qui, `base` = del gioco) e dimensione."""

    path: str
    layer: str
    size: int


class FileContent(AliasedBaseModel):
    """Il testo di un file di contenuti."""

    path: str
    layer: str
    text: str


class FileBody(AliasedBaseModel):
    """Il testo da scrivere in un file."""

    text: str


class SkillBody(AliasedBaseModel):
    """Skill da creare o modificare: solo i campi inviati; `advanced` e' il YAML degli altri campi (`levels`, `effects`, `messages`, ...)."""

    skill_id: str | None = None
    kind: str | None = None
    name: str | None = None
    description: str | None = None
    disabled: bool | None = None
    mana: int | None = None
    beats: int | None = None
    fail: int | None = None
    min_position: str | None = None
    violent: bool | None = None
    max_learn: int | None = None
    saving: str | None = None
    element: str | None = None
    targets: list[str] | None = None
    advanced: str | None = None


class SkillItem(SkillBody):
    """Una skill come restituita dall'API."""

    skill_id: str
    layer: str = "base"
    levels: dict[str, int] = {}
    error: str | None = None
    """Il file non si legge (YAML o forma errati): solo id e messaggio."""


class SocialBody(AliasedBaseModel):
    """Un social: alias, posizione minima, testi per lingua (chiavi: `no_arg`, `found`, `others_found`, ...)."""

    aliases: list[str] = []
    position: str = "resting"
    victim_min_position: int = 0
    hide: bool = False
    messages: dict[str, dict[str, str]] = {}


class SocialItem(SocialBody):
    """Un social come restituito dall'API."""

    name: str
    layer: str = "base"


@router.get("/files/{area}", response_model=list[FileEntry])
async def list_content_files(area: AreaParam, adapter: PachimudDep) -> list[dict[str, Any]]:
    """I file di `tables` (senza i social), `locales` (cataloghi dei messaggi) o `texts` (testi lunghi), strati fusi."""
    return files_store.list_files(_layers(adapter), area)


@router.get("/files/{area}/{rel:path}", response_model=FileContent)
async def get_content_file(area: AreaParam, rel: FilePath, adapter: PachimudDep) -> dict[str, Any]:
    """Il testo di un file (strato dell'utente, altrimenti base). 404 `content.not_found`, 422 `content.invalid_path`."""
    return files_store.read_file(_layers(adapter), area, rel)


@router.put("/files/{area}/{rel:path}", response_model=FileContent)
async def put_content_file(area: AreaParam, rel: FilePath, body: FileBody, adapter: PachimudDep) -> dict[str, Any]:
    """Crea o sostituisce il file nello strato dell'utente. I `.yaml` devono leggersi (422 `content.invalid` con riga e colonna)."""
    return files_store.write_file(_layers(adapter), area, rel, body.text)


@router.delete("/files/{area}/{rel:path}", status_code=204, response_model=None, skip_envelope=True)
async def delete_content_file(area: AreaParam, rel: FilePath, adapter: PachimudDep) -> None:
    """Elimina il file dello strato dell'utente (ripristina quello di base, se c'e'). 404 se non e' dell'utente."""
    files_store.delete_file(_layers(adapter), area, rel)


@router.get("/skills", response_model=list[SkillItem])
async def list_skills(adapter: PachimudDep) -> list[dict[str, Any]]:
    """Le skill (incantesimi e abilita') di tutti gli strati, per id."""
    return files_store.list_skills(_layers(adapter))


@router.post("/skills", response_model=SkillItem, status_code=201)
async def create_skill(body: SkillBody, adapter: PachimudDep) -> dict[str, Any]:
    """Crea `skills/<skillId>.yaml` nello strato dell'utente. 409 `content.id_taken`, 422 `content.invalid_id|invalid`."""
    return files_store.save_skill(_layers(adapter), body.skill_id or "", _fields(body), body.advanced, create=True)


@router.get("/skills/{item_id}", response_model=SkillItem)
async def get_skill(item_id: IdParam, adapter: PachimudDep) -> dict[str, Any]:
    """Una skill con i campi avanzati (`advanced`, YAML). 404 `content.not_found`."""
    return files_store.get_skill(_layers(adapter), item_id)


@router.put("/skills/{item_id}", response_model=SkillItem)
async def update_skill(item_id: IdParam, body: SkillBody, adapter: PachimudDep) -> dict[str, Any]:
    """Aggiorna i campi inviati nello strato dell'utente (una skill solo di base ne viene copiata li'), commenti salvi."""
    return files_store.save_skill(_layers(adapter), item_id, _fields(body), body.advanced, create=False)


@router.delete("/skills/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_skill(item_id: IdParam, adapter: PachimudDep) -> None:
    """Elimina la skill dallo strato dell'utente (404 se esiste solo nella base del gioco)."""
    files_store.delete_skill(_layers(adapter), item_id)


def _fields(body: SkillBody) -> dict[str, Any]:
    """I soli campi semplici inviati dal client (`None` esplicito = toglie la chiave)."""
    return {k: v for k, v in body.model_dump(exclude_unset=True, by_alias=False).items() if k in files_store.SKILL_SCALARS}


@router.get("/socials", response_model=list[SocialItem])
async def list_socials(adapter: PachimudDep) -> list[dict[str, Any]]:
    """I social (`tables/socials*.yaml`, strati e lingue fusi), per nome."""
    return files_store.list_socials(_layers(adapter))


@router.post("/socials/{item_id}", response_model=SocialItem, status_code=201)
async def create_social(item_id: IdParam, body: SocialBody, adapter: PachimudDep) -> dict[str, Any]:
    """Crea un social in `tables/socials.yaml` dello strato dell'utente. 409 `content.id_taken`."""
    return files_store.save_social(_layers(adapter), item_id, body.model_dump(by_alias=False), create=True)


@router.put("/socials/{item_id}", response_model=SocialItem)
async def update_social(item_id: IdParam, body: SocialBody, adapter: PachimudDep) -> dict[str, Any]:
    """Scrive il social (tutti i campi) nello strato dell'utente, anche se esisteva solo nella base."""
    return files_store.save_social(_layers(adapter), item_id, body.model_dump(by_alias=False), create=False)


@router.delete("/socials/{item_id}", status_code=204, response_model=None, skip_envelope=True)
async def delete_social(item_id: IdParam, adapter: PachimudDep) -> None:
    """Toglie il social dallo strato dell'utente (ripristina quello di base, se c'e')."""
    files_store.delete_social(_layers(adapter), item_id)
