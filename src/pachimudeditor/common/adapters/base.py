"""Interfaccia `WorldAdapter`: tutto cio' che l'editor chiede a un "mondo" (un MUD con i suoi dati).

I router dell'editor sono sottili: leggono la richiesta, chiamano un metodo dell'adapter attivo
(vedi `common.adapters.registry.AdapterDep`) e restituiscono il DTO. L'adapter incapsula dove e come
vivono i dati (database SQLAlchemy, file `.are`, ...). Vedi `docs/adapters/index.md`.

Convenzioni:

- Nessun tipo SQLAlchemy attraversa l'interfaccia: argomenti e ritorni sono i DTO di
  `common.adapters.models`.
- `id` e' deciso dall'adapter: pachimud usa la chiave primaria della riga, un adapter su file usa
  `id == vnum` (nello stesso mondo il vnum e' l'identita' stabile). Gli `id` sono opachi per il client.
- Gli errori sono `HTTPException` con codice stabile (`common.editor.errors.not_found/conflict`,
  `pachifast.i18n.api_error`): stesso catalogo i18n per ogni adapter (`zones.not_found`, ...).
- I metodi opzionali (`export_zone_bundle`, `import_zone_dir`) hanno default che alzano 409
  `world.capability_missing`; un adapter li abilita dichiarando la capability corrispondente.
- Un adapter `read_only` deve rifiutare comunque le scritture (409 `world.read_only`): il router lo
  controlla prima (`WriteAdapterDep`), ma l'adapter e' l'ultima difesa.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse
from pydantic import Field

from pachimudeditor.common.adapters.models import (
    ContentRef,
    EntityKind,
    ExitIn,
    ExitOut,
    ExitPatch,
    ExtraDescriptionIn,
    ExtraDescriptionOut,
    ExtraDescriptionPatch,
    ImportPreview,
    MobIn,
    MobOut,
    MobPageParams,
    MobPatch,
    NextZoneVnum,
    ObjectIn,
    ObjectOut,
    ObjectPageParams,
    ObjectPatch,
    Option,
    ResetCommandOut,
    ResetDraftScriptIn,
    ResetScriptIn,
    ResetUsage,
    ResetValidation,
    RoomCloneIn,
    RoomDetail,
    RoomGraph,
    RoomIn,
    RoomOut,
    RoomPageParams,
    RoomPatch,
    ZoneBundle,
    ZoneCloneIn,
    ZoneIn,
    ZoneOut,
    ZonePageParams,
    ZonePatch,
    ZoneSummary,
)

ResourceType = Literal["zone", "room", "mob", "object", "exit", "extra_description", "reset_command"]
"""Tipi di risorsa che un adapter puo' esporre."""


class AdapterCapabilities(AliasedBaseModel):
    """Cosa sa fare un adapter oltre al nucleo (zone/stanze/mob/oggetti, sempre presente)."""

    read_only: bool = False
    """Ogni scrittura e' rifiutata (409 `world.read_only`)."""
    supports_world_overview: bool = False
    """`/api/world`: panoramica, grafo tra zone, ricerca globale."""
    supports_instances: bool = False
    """`/api/instances`: istanze vive di mob/oggetti."""
    supports_players: bool = False
    """`/api/players`: account, personaggi, inventario."""
    supports_transfer: bool = False
    """`export_zone_bundle`/`import_zone_dir` (cartella YAML di zona)."""
    supports_content_races: bool = False
    """`/api/content`: razze e classi come YAML."""
    supports_reset_scripts: bool = True
    """Zone con script di reset modificabile."""
    supports_extra_descriptions: bool = True
    """Stanze con extra description."""


class FieldDescriptor(AliasedBaseModel):
    """Un campo di un'entita' (per generare form generici sul frontend)."""

    name: str
    """Nome camelCase nel DTO."""
    type: Literal["int", "string", "text", "bool", "enum", "flags", "list", "dict", "number"] = "string"
    required: bool = False
    read_only: bool = False
    enum: str | None = None
    """Per `enum`/`flags`: nome della lista in `GET /api/meta/enums` da cui prendere le opzioni."""
    nullable: bool = False
    unsupported: bool = False
    """Il mondo non ha il campo: in lettura e' neutro, in scrittura accetta solo il valore neutro (422 `*.field_unsupported`)."""


ExtraKind = Literal["text", "number", "boolean", "flags", "enum", "select", "json"]
"""Editor di una chiave di `extra`: `flags` = lista di nomi; `enum` = nome (label) dell'opzione; `select` = valore (indice)."""


class ExtraFieldDescriptor(AliasedBaseModel):
    """Una chiave di `extra` di una risorsa (per generare il form dei campi specifici del MUD)."""

    name: str
    """Chiave in `extra` (camelCase)."""
    label_key: str
    """Chiave i18n dell'etichetta (`extra.labels.<name>`); il frontend ripiega sul nome se manca."""
    type: ExtraKind = "text"
    enum: str | None = None
    """Per `flags`/`enum`/`select`: lista di `GET /api/meta/enums` da cui prendere le opzioni."""
    read_only: bool = False
    nullable: bool = False
    """Il testo vuoto vale `null`."""
    group: str | None = None
    """Sezione del form (`diagnostic` = avvisi dell'adapter, mai modificabili, mostrati come banner)."""


class ResourceInfo(AliasedBaseModel):
    """Una risorsa esposta dall'adapter e i campi della sua entita'."""

    type: ResourceType
    fields: list[FieldDescriptor] = Field(default_factory=list)
    extra_fields: list[ExtraFieldDescriptor] = Field(default_factory=list)
    """Le chiavi di `extra` che l'adapter emette (vuote: `extra` e' sempre `{}`)."""
    create_at_end: bool = False
    """Zone: una zona nuova si aggiunge solo in coda (il range di partenza e' derivato, non modificabile)."""


class AdapterInfo(AliasedBaseModel):
    """Identita' e struttura di un mondo, restituita da `GET /api/worlds`."""

    id: str
    kind: str
    name: str
    resources: list[ResourceInfo] = Field(default_factory=list)
    capabilities: AdapterCapabilities = Field(default_factory=AdapterCapabilities)
    default: bool = False
    params: dict[str, str | int | bool | None] = Field(default_factory=dict)
    """Parametri informativi del mondo (es. `data_prefix`); additivo, vuoto se l'adapter non ne espone."""


class WorldAdapter(ABC):
    """Contratto che ogni backend di mondo deve implementare. Tutti i metodi di dati sono `async`."""

    # ------------------------------------------------------------------ identita'

    @abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Le capability dichiarate (sincrono, nessun I/O)."""

    @abstractmethod
    def describe(self) -> AdapterInfo:
        """Id, tipo, nome e descrittori dei campi per risorsa (sincrono, nessun I/O)."""

    async def close(self) -> None:
        """Rilascia le risorse dell'adapter (engine, connessioni): chiamato allo spegnimento. Default: niente."""

    def check_texts(self, texts: Iterable[str], *, zone_id: int | None) -> None:
        """Verifica (prima di una conversione) che i testi siano scrivibili nel mondo; 422 con il codice dell'adapter.

        `zone_id` e' la zona di arrivo gia' esistente che verrebbe riscritta (`None` = zona nuova). Default: niente."""

    # ------------------------------------------------------------------ zone

    @abstractmethod
    async def list_zones(self, params: ZonePageParams) -> PaginatedResponse[ZoneOut]:
        """Zone paginate, cercabili per nome/builder/vnum; ordine di default per vnum."""

    @abstractmethod
    async def get_zone(self, zone_id: int) -> ZoneOut:
        """Una zona (404 `zones.not_found`)."""

    @abstractmethod
    async def create_zone(self, data: ZoneIn) -> ZoneOut:
        """Crea una zona (409 `zones.vnum_taken`)."""

    @abstractmethod
    async def update_zone(self, zone_id: int, data: ZonePatch) -> ZoneOut:
        """Aggiornamento parziale; range finali coerenti (422 `zones.invalid_*_range`), vnum libero."""

    @abstractmethod
    async def delete_zone(self, zone_id: int) -> None:
        """Elimina (con il suo script di reset); 409 `zones.not_empty` se ha ancora contenuto."""

    @abstractmethod
    async def zone_summary(self, zone_id: int) -> ZoneSummary:
        """Conteggi di stanze, mob e oggetti."""

    @abstractmethod
    async def next_zone_vnum(self, span: int) -> NextZoneVnum:
        """Un vnum di zona libero e un range di ampiezza `span` che non si sovrappone ad altre zone."""

    @abstractmethod
    async def next_content_vnum(self, zone_id: int, kind: EntityKind) -> int:
        """Un vnum libero per una nuova stanza/mob/oggetto della zona."""

    @abstractmethod
    async def clone_zone(self, zone_id: int, data: ZoneCloneIn) -> ZoneOut:
        """Duplica la zona (non il contenuto), opzionalmente con lo script di reset."""

    @abstractmethod
    async def list_reset_commands(self, zone_id: int) -> list[ResetCommandOut]:
        """Lo script di reset della zona, in ordine."""

    @abstractmethod
    async def replace_reset_commands(self, zone_id: int, data: ResetScriptIn) -> list[ResetCommandOut]:
        """Sostituisce lo script (422 `zones.reset_*` se un vnum non esiste); rinumera `orderIndex`."""

    @abstractmethod
    async def validate_reset_commands(self, zone_id: int, data: ResetDraftScriptIn) -> ResetValidation:
        """Valida uno script senza salvarlo (usa `common.adapters.rules.validate_script`)."""

    # ------------------------------------------------------------------ stanze

    @abstractmethod
    async def list_rooms(self, params: RoomPageParams) -> PaginatedResponse[RoomOut]:
        """Stanze paginate, filtro `zoneId`, ricerca nome/vnum."""

    @abstractmethod
    async def get_room(self, room_id: int) -> RoomDetail:
        """Una stanza con uscite ed extra description."""

    @abstractmethod
    async def create_room(self, data: RoomIn) -> RoomDetail:
        """Crea una stanza (409 `rooms.vnum_taken`)."""

    @abstractmethod
    async def update_room(self, room_id: int, data: RoomPatch) -> RoomDetail:
        """Aggiornamento parziale; cambiare vnum e' 409 `rooms.vnum_in_use` se un reset lo usa."""

    @abstractmethod
    async def delete_room(self, room_id: int) -> None:
        """Elimina stanza, uscite ed extra; 409 `rooms.in_reset_usage` / `rooms.has_instances`."""

    @abstractmethod
    async def clone_room(self, room_id: int, data: RoomCloneIn) -> RoomDetail:
        """Duplica la stanza (senza uscite, con extra description)."""

    @abstractmethod
    async def room_graph(self, zone_id: int) -> RoomGraph:
        """Nodi e archi delle stanze della zona (`common.adapters.rules.build_room_graph`)."""

    @abstractmethod
    async def room_usage(self, room_id: int) -> list[ResetUsage]:
        """I reset che referenziano la stanza per vnum."""

    @abstractmethod
    async def create_exit(self, room_id: int, data: ExitIn) -> ExitOut:
        """Crea un'uscita (una per direzione; coerenza con `rules.check_exit`)."""

    @abstractmethod
    async def update_exit(self, room_id: int, exit_id: int, data: ExitPatch) -> ExitOut:
        """Aggiornamento parziale di un'uscita."""

    @abstractmethod
    async def delete_exit(self, room_id: int, exit_id: int) -> None:
        """Elimina un'uscita."""

    @abstractmethod
    async def create_extra_description(self, room_id: int, data: ExtraDescriptionIn) -> ExtraDescriptionOut:
        """Crea un'extra description."""

    @abstractmethod
    async def update_extra_description(self, room_id: int, extra_id: int, data: ExtraDescriptionPatch) -> ExtraDescriptionOut:
        """Aggiornamento parziale di un'extra description."""

    @abstractmethod
    async def delete_extra_description(self, room_id: int, extra_id: int) -> None:
        """Elimina un'extra description."""

    # ------------------------------------------------------------------ mob

    @abstractmethod
    async def list_mobs(self, params: MobPageParams) -> PaginatedResponse[MobOut]:
        """Mob paginati, filtro `zoneId`."""

    @abstractmethod
    async def get_mob(self, mob_id: int) -> MobOut:
        """Un mob prototype."""

    @abstractmethod
    async def create_mob(self, data: MobIn) -> MobOut:
        """Crea un mob prototype (409 `mobs.vnum_taken`)."""

    @abstractmethod
    async def update_mob(self, mob_id: int, data: MobPatch) -> MobOut:
        """Aggiornamento parziale; cambiare vnum e' 409 `mobs.vnum_in_use` se un reset lo usa."""

    @abstractmethod
    async def delete_mob(self, mob_id: int) -> None:
        """Elimina; 409 `mobs.in_reset_usage` / `mobs.has_instances`."""

    @abstractmethod
    async def mob_usage(self, mob_id: int) -> list[ResetUsage]:
        """I reset che referenziano il mob per vnum."""

    # ------------------------------------------------------------------ oggetti

    @abstractmethod
    async def list_objects(self, params: ObjectPageParams) -> PaginatedResponse[ObjectOut]:
        """Oggetti paginati, filtro `zoneId`."""

    @abstractmethod
    async def get_object(self, object_id: int) -> ObjectOut:
        """Un object prototype."""

    @abstractmethod
    async def create_object(self, data: ObjectIn) -> ObjectOut:
        """Crea un object prototype (409 `objects.vnum_taken`)."""

    @abstractmethod
    async def update_object(self, object_id: int, data: ObjectPatch) -> ObjectOut:
        """Aggiornamento parziale; cambiare vnum e' 409 `objects.vnum_in_use`."""

    @abstractmethod
    async def delete_object(self, object_id: int) -> None:
        """Elimina; 409 `objects.in_reset_usage` / `objects.in_exit_key_usage` / `objects.has_instances`."""

    @abstractmethod
    async def object_usage(self, object_id: int) -> list[ResetUsage]:
        """I reset (e le chiavi di uscite) che referenziano l'oggetto per vnum."""

    # ------------------------------------------------------------------ meta

    @abstractmethod
    async def enums(self) -> dict[str, list[Option]]:
        """`{nome: [{value, label}]}` per ogni enum/flag che i form usano."""

    @abstractmethod
    async def races(self) -> list[ContentRef]:
        """Razze del mondo (lista vuota se il MUD non le ha)."""

    @abstractmethod
    async def classes(self) -> list[ContentRef]:
        """Classi del mondo (lista vuota se il MUD non le ha)."""

    # ------------------------------------------------------------------ opzionali

    async def export_zone_bundle(self, zone_id: int) -> ZoneBundle:
        """I file YAML di una zona come testo (capability `supports_transfer`)."""
        raise api_error(409, "world.capability_missing", capability="supports_transfer")

    async def import_zone_dir(self, directory: Path, *, dry_run: bool, confirm: bool) -> ImportPreview:
        """Anteprima/import di una cartella con i file di zona gia' staged (capability `supports_transfer`).

        Con `dry_run` non scrive nulla; l'import vero richiede `confirm` (422 `transfer.confirm_required`).
        """
        raise api_error(409, "world.capability_missing", capability="supports_transfer")

    async def aclose(self) -> None:
        """Rilascia risorse (connessioni, file aperti). Default: niente."""


__all__ = [
    "AdapterCapabilities",
    "AdapterInfo",
    "FieldDescriptor",
    "ResourceInfo",
    "ResourceType",
    "WorldAdapter",
]
