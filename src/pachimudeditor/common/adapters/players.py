"""Giocatori dei MUD su file (SDK 1.3 lettura, 1.4 scrittura): DTO neutri, descrittore dichiarativo e mixin opzionale `PlayersAdapter`.

L1 elenco, L2 dettaglio + inventario/equipaggiamento (1.3); L3 scrittura dei campi e dell'inventario (1.4). L'`id` di un giocatore
e' opaco per il client (file: il nome del file senza estensione). Mai password o hash nei DTO: solo `has_password`.
"""

from datetime import datetime
from typing import Any, Literal

from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pachifast.schemas.responses import PageParams, PaginatedResponse
from pydantic import Field

from pachimudeditor.common.adapters.base import ExtraFieldDescriptor
from pachimudeditor.common.adapters.models import NeutralOut

ColumnType = Literal["text", "number", "datetime", "boolean", "duration"]
"""Come il frontend formatta il valore di una colonna (`duration` = secondi)."""


class PlayerSummary(NeutralOut):
    """Una riga dell'elenco giocatori: campi comuni; il resto del MUD sta in `extra` (descritto da `PlayersInfo`)."""

    id: str
    name: str
    level: int | None = None
    class_label: str | None = None
    race_label: str | None = None
    sex: str | None = None
    gold: int | None = None
    room_vnum: int | None = None
    last_login_at: datetime | None = None
    played_seconds: int | None = None
    has_password: bool | None = None
    """Esiste una password nel file (mai il valore). `None` = non determinabile."""
    online: bool | None = None
    """`True`/`False` solo se il MUD sa dirlo con certezza (SDK 1.5: canale live); `None` = sconosciuto (il caso normale su file)."""
    problem: str | None = None
    """Codice stabile se il file e' illeggibile/corrotto (`bad_size`, ...): la riga resta visibile, senza dati."""
    revision: str | None = None
    """Impronta del file letto (SDK 1.4): da rimandare in `PlayerWriteOptions.revision` per rilevare modifiche concorrenti."""


class PlayerDetail(PlayerSummary):
    """Il dettaglio: i campi di `PlayersInfo.detail_fields` in `details`, le tabelle di `detail_lists` in `lists`."""

    details: dict[str, Any] = Field(default_factory=dict)
    lists: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class PlayerItem(AliasedBaseModel):
    """Un oggetto portato (inventario, `wear_slot` nullo) o equipaggiato; `depth` > 0 = dentro un contenitore."""

    id: int
    """Posizione nel file (stabile finche' il file non cambia)."""
    vnum: int | None = None
    name: str = ""
    keywords: str = ""
    wear_slot: str | None = None
    depth: int = 0
    known: bool = False
    """`True` se il prototipo esiste nel mondo (il nome viene dal prototipo)."""
    extra: dict[str, Any] = Field(default_factory=dict)


class PlayerInventory(AliasedBaseModel):
    """Inventario e equipaggiamento di un giocatore, con i dati del file e un eventuale problema di lettura."""

    items: list[PlayerItem] = Field(default_factory=list)
    problem: str | None = None
    """Codice stabile (`truncated`, `too_many_items`, `owner_mismatch`, ...): gli oggetti leggibili sono comunque elencati."""
    revision: str | None = None
    """Impronta del file dell'inventario (SDK 1.4), come `PlayerSummary.revision`."""
    extra: dict[str, Any] = Field(default_factory=dict)


class PlayerColumn(AliasedBaseModel):
    """Una colonna dell'elenco: `name` e' un campo di `PlayerSummary` oppure, con `source == "extra"`, una chiave di `extra`."""

    name: str
    label_key: str
    type: ColumnType = "text"
    sortable: bool = False
    source: Literal["field", "extra"] = "field"


class PlayerListColumn(AliasedBaseModel):
    """Una colonna di una tabella del dettaglio (`PlayerListInfo`)."""

    name: str
    label_key: str
    type: ColumnType = "text"


class PlayerListInfo(AliasedBaseModel):
    """Una tabella del dettaglio (es. abilita', affect): righe in `PlayerDetail.lists[name]`."""

    name: str
    label_key: str
    columns: list[PlayerListColumn] = Field(default_factory=list)


class PlayersInfo(AliasedBaseModel):
    """Descrittore dichiarativo dei giocatori di un mondo (`GET /api/world/players/info`)."""

    columns: list[PlayerColumn] = Field(default_factory=list)
    detail_fields: list[ExtraFieldDescriptor] = Field(default_factory=list)
    """Campi di `PlayerDetail.details`; `group` = sezione (se manca: «generale»)."""
    detail_lists: list[PlayerListInfo] = Field(default_factory=list)
    has_accounts: bool = False
    online_policy: Literal["unknown", "warn"] = "unknown"
    """`warn`: il frontend mostra l'avviso «il server potrebbe essere in esecuzione» (lettura sempre permessa)."""
    wear_slots: list[str] = Field(default_factory=list)
    """Gli slot di equipaggiamento ammessi (SDK 1.4), nell'ordine del MUD: i valori di `PlayerItem.wear_slot` e di `PlayerItemAdd.wear_slot`."""


class PlayersStatus(AliasedBaseModel):
    """Stato del server di gioco, se rilevabile (`GET /api/world/players/status`)."""

    server_running: bool | None = None
    """`None` = non rilevabile (altro utente, altra macchina, sistema senza /proc)."""
    detection: str = "none"
    """Come e' stato rilevato (`proc`, `none`): informativo."""


class PlayerPageParams(PageParams):
    """Parametri dell'elenco: `search` sul nome; ordinamento sui campi di `PlayerSummary` (default: nome)."""

    search_fields = ["name"]
    order_fields = ["id", "name", "level", "class_label", "race_label", "gold", "room_vnum", "last_login_at", "played_seconds"]


class PlayerWriteOptions(AliasedBaseModel):
    """Opzioni comuni di ogni scrittura (SDK 1.4)."""

    revision: str | None = None
    """La `revision` letta: se il file e' cambiato nel frattempo la scrittura e' rifiutata (409 `worldplayers.conflict`). `None` = nessun controllo."""
    confirm_server_running: bool = False
    """Obbligatorio se `GET /status` dice `serverRunning: true` (altrimenti 409 `worldplayers.server_running`)."""


class PlayerPatch(PlayerWriteOptions):
    """Modifica parziale del dettaglio: solo i campi presenti cambiano. Le chiavi sono quelle di `PlayersInfo.detail_fields`
    non `read_only` (`details`) e delle `detail_lists` (`lists`, sostituzione dell'intera tabella)."""

    details: dict[str, Any] = Field(default_factory=dict)
    lists: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


class PlayerItemAdd(PlayerWriteOptions):
    """Aggiunge un oggetto dal prototipo del mondo (`vnum`)."""

    vnum: int
    wear_slot: str | None = None
    """Uno di `PlayersInfo.wear_slots`; `None` = portato."""
    container_id: int | None = None
    """`PlayerItem.id` del contenitore in cui metterlo (incompatibile con `wear_slot`)."""


class PlayerItemUpdate(PlayerWriteOptions):
    """Cambia lo slot di un oggetto di primo livello."""

    wear_slot: str | None
    """Il nuovo slot (uno di `PlayersInfo.wear_slots`) oppure `None` = portato; obbligatorio."""


class PlayersAdapter:
    """Mixin opzionale di un `WorldAdapter` con giocatori leggibili. Default: 409 `world.capability_missing`.

    Va dichiarata la capability `supports_player_records` (e `supports_player_inventory` se c'e' l'inventario); le scritture (1.4)
    richiedono `supports_player_write` / `supports_player_inventory_write`.
    Gli id non validi o inesistenti sono 404 `worldplayers.not_found` (un adapter su file deve validarli contro il path traversal).
    """

    def players_info(self) -> PlayersInfo:
        """Colonne dell'elenco e campi del dettaglio (sincrono, nessun I/O)."""
        raise api_error(409, "world.capability_missing", capability="supports_player_records")

    async def players_status(self) -> PlayersStatus:
        """Stato del server di gioco (best effort)."""
        return PlayersStatus()

    async def player_connected(self, player_id: str) -> bool | None:
        """Il giocatore e' connesso adesso? (SDK 1.5, tipicamente via canale live.) `True` = certo: la scrittura su file richiede la conferma
        «server acceso» anche se `players_status` non rileva nulla. `False`/`None` = non lo si sa (o non e' connesso): resta l'avviso
        best-effort di `players_status`. Mai un'eccezione: un canale spento vale `None`."""
        return None

    async def list_players(self, params: PlayerPageParams) -> PaginatedResponse[PlayerSummary]:
        """Giocatori paginati."""
        raise api_error(409, "world.capability_missing", capability="supports_player_records")

    async def get_player(self, player_id: str) -> PlayerDetail:
        """Il dettaglio di un giocatore (404 `worldplayers.not_found`)."""
        raise api_error(409, "world.capability_missing", capability="supports_player_records")

    async def player_inventory(self, player_id: str) -> PlayerInventory:
        """Inventario ed equipaggiamento (capability `supports_player_inventory`)."""
        raise api_error(409, "world.capability_missing", capability="supports_player_inventory")

    async def update_player(self, player_id: str, patch: PlayerPatch) -> PlayerDetail:
        """Modifica i campi (capability `supports_player_write`). 409 `worldplayers.conflict` se la `revision` non e' piu' quella del
        file, 422 `worldplayers.invalid_value` per un valore non valido. Il core ha gia' controllato `read_only` e il server acceso."""
        raise api_error(409, "world.capability_missing", capability="supports_player_write")

    async def add_player_item(self, player_id: str, item: PlayerItemAdd) -> PlayerInventory:
        """Aggiunge un oggetto (capability `supports_player_inventory_write`)."""
        raise api_error(409, "world.capability_missing", capability="supports_player_inventory_write")

    async def update_player_item(self, player_id: str, item_id: int, change: PlayerItemUpdate) -> PlayerInventory:
        """Cambia lo slot di un oggetto (capability `supports_player_inventory_write`)."""
        raise api_error(409, "world.capability_missing", capability="supports_player_inventory_write")

    async def remove_player_item(self, player_id: str, item_id: int, options: PlayerWriteOptions) -> PlayerInventory:
        """Toglie un oggetto con il suo contenuto (capability `supports_player_inventory_write`)."""
        raise api_error(409, "world.capability_missing", capability="supports_player_inventory_write")


__all__ = [
    "ColumnType",
    "PlayerColumn",
    "PlayerDetail",
    "PlayerInventory",
    "PlayerItem",
    "PlayerListColumn",
    "PlayerItemAdd",
    "PlayerItemUpdate",
    "PlayerListInfo",
    "PlayerPageParams",
    "PlayerPatch",
    "PlayerWriteOptions",
    "PlayerSummary",
    "PlayersAdapter",
    "PlayersInfo",
    "PlayersStatus",
]
