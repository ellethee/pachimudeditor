"""Canale live verso un MUD acceso (SDK 1.5): DTO neutri, errori con codici stabili e mixin opzionale `LiveAdapter`.

Protocollo `livectl` v1 (`docs/backend/live-control-protocol.md`). Il client riusabile e' in `live_client.py`; qui sta tutto cio' che
attraversa l'interfaccia dell'adapter. Mai il token, ne' il percorso del socket, in un DTO, in un errore o in un log.
"""

import re
from contextlib import contextmanager
from typing import Any, Iterator, Literal

from fastapi import HTTPException
from pachifast.database import AliasedBaseModel
from pachifast.i18n import api_error
from pydantic import Field, model_validator

LIVE_NAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,19}")
"""Nome di un personaggio ammesso dal protocollo (stessa regola dei file)."""

IMMORTAL_LEVEL = 51
"""Da questo livello in su un personaggio e' un immortale: la promozione richiede `confirm_immortal`."""


class LiveError(Exception):
    """Errore del canale: `code` e' il codice del protocollo (`not_found`, `value_out_of_range`, ...) oppure uno locale
    (`unreachable`, `timeout`, `outcome_unknown`, `token_missing`, `response_too_large`, `request_too_large`, `protocol_error`).

    `params` viene dal MUD (mai dal client) e contiene solo campi dichiarati dal protocollo (`field`, `min`, `max`, `reason`, ...).
    Il messaggio non contiene mai token o percorsi.
    """

    def __init__(self, code: str, message: str = "", **params: Any) -> None:
        """Memorizza codice, messaggio (solo per i log) e parametri."""
        super().__init__(f"{code}: {message}" if message else code)
        self.code, self.message, self.params = code, message, params


_PLAIN: dict[str, tuple[int, str]] = {
    "not_found": (404, "worldlive.not_found"),
    "player_not_playing": (409, "worldlive.player_not_playing"),
    "player_busy": (409, "worldlive.player_busy"),
    "bad_params": (422, "worldlive.bad_params"),
    "stale_ref": (409, "worldlive.stale_ref"),
    "bad_request": (422, "worldlive.bad_params"),
    "unencodable_text": (422, "worldlive.unencodable_text"),
    "value_out_of_range": (422, "worldlive.value_out_of_range"),
    "command_disabled": (409, "worldlive.command_disabled"),
    "unknown_command": (409, "worldlive.command_disabled"),
    "rate_limited": (429, "worldlive.rate_limited"),
    "busy": (503, "worldlive.busy"),
    "too_many_connections": (503, "worldlive.busy"),
    "reload_failed": (409, "worldlive.reload_failed"),
    "unavailable": (503, "worldlive.unavailable"),
    "unreachable": (503, "worldlive.unreachable"),
    "auth_failed": (503, "worldlive.auth_failed"),
    "token_missing": (503, "worldlive.token_missing"),
    "timeout": (504, "worldlive.timeout"),
    "outcome_unknown": (504, "worldlive.outcome_unknown"),
    "response_too_large": (502, "worldlive.protocol_error"),
    "request_too_large": (422, "worldlive.bad_params"),
    "protocol_unsupported": (502, "worldlive.protocol_unsupported"),
}
_REASONS: dict[str, tuple[int, str]] = {
    "immortal_level": (409, "worldlive.immortal_confirmation_required"),
    "class_not_owned": (409, "worldlive.class_not_owned"),
    "zone_zero": (409, "worldlive.zone_forbidden"),
    "deny_list": (409, "worldlive.object_denied"),
}


def http_error(error: LiveError) -> HTTPException:
    """Traduce un `LiveError` in `HTTPException` con codice stabile `worldlive.*` e parametri per il messaggio.

    Codici non previsti (anche futuri del protocollo) diventano 502 `worldlive.protocol_error`.
    """
    p = error.params
    if error.code == "forbidden_by_policy":
        status, code = _REASONS.get(str(p.get("reason")), (409, "worldlive.forbidden_by_policy"))
        return api_error(
            status, code, reason=p.get("reason", ""), level=p.get("level", ""), class_name=p.get("class", ""), vnum=p.get("vnum", "")
        )
    if error.code == "reload_failed" and "errors" in p:  # i problemi (file e riga) viaggiano nei parametri dell'errore
        if "zone" in p:  # `zone.reload`: l'adapter li ha ricavati da `content.validate` (il gioco manda solo `zone`)
            return api_error(409, "worldlive.reload_failed", zone=p["zone"], issues=_issues(p["errors"]), proto=error.code)
        return api_error(409, "worldlive.content_reload_failed", kind=p.get("kind", ""), issues=_issues(p["errors"]), proto=error.code)
    status, code = _PLAIN.get(error.code, (502, "worldlive.protocol_error"))
    if error.code == "bad_params" and p.get("field") and p.get("max") not in (None, ""):
        code = "worldlive.value_too_long"  # testo oltre il limite del rent: `max` e' in byte
    return api_error(
        status, code, field=p.get("field", ""), min=p.get("min", ""), max=p.get("max", ""), what=p.get("what", ""), zone=p.get("zone", ""),
        retry_after_ms=p.get("retry_after_ms", ""), proto=error.code,
    )  # fmt: skip


def _issues(raw: Any) -> list[dict[str, Any]]:
    """I problemi di `content.reload` come elenco di `dict` (voci non valide scartate)."""
    return (
        [LiveContentIssue.model_validate(i).model_dump(by_alias=True) for i in raw if isinstance(i, dict)] if isinstance(raw, list) else []
    )


@contextmanager
def live_errors() -> Iterator[None]:
    """Contesto per le rotte: i `LiveError` diventano `HTTPException` (vedi `http_error`)."""
    try:
        yield
    except LiveError as error:
        raise http_error(error) from error


# ---------------------------------------------------------------------------------------------------------------- DTO

LiveState = Literal["connected", "unreachable", "auth_failed", "token_missing", "error"]


class LiveStatus(AliasedBaseModel):
    """Stato del canale (`GET /api/world/live/status`): sempre una risposta, mai un errore."""

    state: LiveState
    reachable: bool = False
    code: str | None = None
    """Codice `worldlive.*` del motivo se non e' `connected`."""
    protocol: int | None = None
    mud: dict[str, Any] = Field(default_factory=dict)
    """`kind`, `name`, `version`, `module` come dichiarati dal MUD."""
    classes: list[str] = Field(default_factory=list)
    """Classi di comandi attive (`read`, `write`)."""
    commands: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    editable_fields: list[str] = Field(default_factory=list)
    """Campi accettati da `player.set` (vuoto se le scritture sono disattivate)."""
    latency_ms: int | None = None


class LiveWhoPlayer(AliasedBaseModel):
    """Un giocatore connesso (`who`). Mai l'indirizzo di rete."""

    name: str
    state: str = "playing"
    """`playing`, `linkdead`, `polymorph`."""
    level: int | None = None
    levels: dict[str, int] = Field(default_factory=dict)
    race: int | str | None = None
    """Numero (dikumod) o id stringa (pachimud: `human`)."""
    sex: int | None = None
    room: int | None = None
    zone: int | None = None
    position: int | None = None
    fighting: bool = False
    idle: int | None = None
    immortal: bool = False
    invisible: int = 0


class LiveWho(AliasedBaseModel):
    """Giocatori connessi."""

    players: list[LiveWhoPlayer] = Field(default_factory=list)
    count: int = 0
    truncated: bool = False


class LiveServerInfo(AliasedBaseModel):
    """Stato del server (`info`)."""

    mud: dict[str, Any] = Field(default_factory=dict)
    started_at: int | None = None
    now: int | None = None
    uptime_s: int | None = None
    pulse: int | None = None
    ticks: int | None = None
    lag_us: int | None = None
    players: dict[str, int] = Field(default_factory=dict)
    world: dict[str, int] = Field(default_factory=dict)


class LiveZone(AliasedBaseModel):
    """Una zona **come la vede il gioco** (`index` e' quello da passare a `zone.reset`; puo' non coincidere con l'id dell'editor)."""

    index: int
    num: int | None = None
    name: str = ""
    bottom: int | None = None
    """Primo vnum della zona (pachimud; dikumod ha solo `top`)."""
    top: int | None = None
    lifespan: int | None = None
    age: int | None = None
    reset_mode: int | None = None
    started: bool | None = None


class LiveZones(AliasedBaseModel):
    """Zone del gioco."""

    zones: list[LiveZone] = Field(default_factory=list)


class LivePlayerState(AliasedBaseModel):
    """Valori **correnti in memoria** di un giocatore connesso (`player.get`)."""

    name: str
    state: str = "playing"
    fields: dict[str, Any] = Field(default_factory=dict)
    editable_fields: list[str] = Field(default_factory=list)


class LivePlayerSetIn(AliasedBaseModel):
    """Modifica live (`player.set`): `fields` ha i nomi del protocollo (`gold`, `levels: {classe: livello}`, `conditions: {...}`)."""

    fields: dict[str, Any] = Field(min_length=1, max_length=16)
    save: bool = True
    """Salva il giocatore con il meccanismo del gioco (`save`); default vero (memoria e file restano allineati)."""
    confirm_immortal: bool = False
    """Obbligatorio per promuovere una classe a >= 51: l'editor lo invia solo dopo la conferma esplicita dell'utente."""


class LiveApplied(AliasedBaseModel):
    """Vecchio e nuovo valore di un campo."""

    old: Any = None
    new: Any = None


class LivePlayerSetOut(AliasedBaseModel):
    """Esito di `player.set`."""

    name: str
    applied: dict[str, LiveApplied] = Field(default_factory=dict)
    saved: bool = False
    warnings: list[str] = Field(default_factory=list)


class LiveZoneResetIn(AliasedBaseModel):
    """Reset di una zona: **una sola** tra `zone` (indice di `zone.list`) e `room` (vnum di una stanza)."""

    zone: int | None = Field(default=None, ge=0)
    room: int | None = Field(default=None, ge=0)
    only_if_empty: bool = False

    @model_validator(mode="after")
    def _one_target(self) -> "LiveZoneResetIn":
        """Esattamente una tra `zone` e `room`."""
        if (self.zone is None) == (self.room is None):
            raise ValueError("serve esattamente uno tra zone e room")
        return self


class LiveZoneResetOut(AliasedBaseModel):
    """Esito di `zone.reset`."""

    zone: int
    name: str = ""
    executed: bool = True


class LiveZoneReloadIn(AliasedBaseModel):
    """Ricarica una zona dai file (`zone.reload`, estensione pachimud): `vnum` e' quello della zona (`zone.list`: `index == num == vnum`)."""

    vnum: int = Field(ge=0)


class LiveZoneReloadOut(AliasedBaseModel):
    """Esito di `zone.reload`: conteggi dei contenuti riletti."""

    zone: int
    name: str = ""
    reloaded: bool = True
    rooms: int = 0
    mobs: int = 0
    objects: int = 0


class LiveContentIssue(AliasedBaseModel):
    """Un problema dei contenuti (`content.validate`, `content.reload`): gravita', codice stabile, messaggio, file e riga (assenti se non c'e' un file)."""

    severity: Literal["error", "warning"] = "error"
    code: str = ""
    message: str = ""
    file: str | None = None
    line: int | None = None


class LiveContentValidateOut(AliasedBaseModel):
    """Esito di `content.validate` (estensione pachimud, sola lettura): come `pachimud validate --json`."""

    ok: bool = True
    errors: int = 0
    warnings: int = 0
    issues: list[LiveContentIssue] = Field(default_factory=list)


ContentKind = Literal["races", "classes", "skills", "tables", "socials", "locales", "all"]
"""Cosa rilegge `content.reload`."""


class LiveContentReloadIn(AliasedBaseModel):
    """Ricarica a caldo dei contenuti (`content.reload`, estensione pachimud)."""

    kind: ContentKind = "all"


class LiveContentReloadOut(AliasedBaseModel):
    """Esito di `content.reload`: id ricaricati per categoria. Se i file non sono validi il gioco non cambia e l'errore e' 409
    `worldlive.content_reload_failed` con i problemi in `issues`."""

    ok: bool = True
    kind: str = "all"
    reloaded: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[LiveContentIssue] = Field(default_factory=list)


class LiveBoardDeleteOut(AliasedBaseModel):
    """Esito di `board.delete` (estensione pachimud): il messaggio e' tolto dal DB e dalla copia in memoria del gioco."""

    ok: bool = True
    board_id: str
    id: int
    remaining: int = 0


class LiveBoardClearOut(AliasedBaseModel):
    """Esito di `board.clear` (estensione pachimud): bacheca svuotata nel DB e nella copia in memoria del gioco."""

    ok: bool = True
    board_id: str
    removed: int = 0


class LiveInstance(AliasedBaseModel):
    """Un'istanza in memoria (`instances.list`): mob o oggetto a terra."""

    instance_id: int | str
    kind: Literal["mob", "obj"]
    vnum: int
    room_vnum: int | None = None


class LiveInstances(AliasedBaseModel):
    """Istanze in memoria per stanza o prototipo (estensione pachimud, sola lettura)."""

    instances: list[LiveInstance] = Field(default_factory=list)
    count: int = 0
    truncated: bool = False


class LiveLoadIn(AliasedBaseModel):
    """Crea mob o oggetti (`load.mob`, `load.obj`): **una sola** destinazione tra `room` e `player`."""

    vnum: int = Field(ge=0)
    room: int | None = Field(default=None, ge=0)
    player: str | None = None
    count: int = Field(default=1, ge=1, le=10)
    notify: bool = False

    @model_validator(mode="after")
    def _one_target(self) -> "LiveLoadIn":
        """Esattamente una tra `room` e `player` (nome valido)."""
        if (self.room is None) == (self.player is None):
            raise ValueError("serve esattamente uno tra room e player")
        if self.player is not None and not LIVE_NAME_RE.fullmatch(self.player):
            raise ValueError("nome del giocatore non valido")
        return self


class LiveLoadOut(AliasedBaseModel):
    """Esito di `load.*`: una voce per istanza creata (`vnum`, `name`, `room` o `where`)."""

    loaded: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    """Avvisi del MUD per `load.obj`: `vnum_not_saveable` (vnum > 32767 a un giocatore: il rent lo corromperebbe al salvataggio)."""


class LiveEchoIn(AliasedBaseModel):
    """Messaggio (`echo`): **una sola** destinazione tra `all`, `player`, `room`."""

    text: str = Field(min_length=1, max_length=400)
    all: bool | None = None
    player: str | None = None
    room: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_target(self) -> "LiveEchoIn":
        """Esattamente una destinazione (`all` solo se vero)."""
        targets = [self.all is True, self.player is not None, self.room is not None]
        if self.all is False or sum(targets) != 1:
            raise ValueError("serve esattamente una destinazione tra all, player e room")
        if self.player is not None and not LIVE_NAME_RE.fullmatch(self.player):
            raise ValueError("nome del giocatore non valido")
        return self


class LiveEchoOut(AliasedBaseModel):
    """Esito di `echo`."""

    recipients: int = 0


class LiveItemAffect(AliasedBaseModel):
    """Un affect di un oggetto istanza (`location` 0 = nessuno)."""

    location: int = Field(default=0, ge=0, le=64)
    modifier: int = Field(default=0, ge=-32768, le=32767)


class LiveItem(AliasedBaseModel):
    """Un oggetto istanza di un giocatore connesso (`player.inventory`, `obj.get`). `ref` e `fp` sono opachi: vanno rimandati cosi' come sono."""

    ref: str
    """Percorso (`eq:5`, `inv:2/0`): cambia quando l'inventario cambia, vale solo con l'`fp` dell'ultima lettura."""
    fp: str
    vnum: int | None = None
    slot: int | None = None
    """Posizione di equipaggiamento (solo primo livello indossato)."""
    depth: int = 0
    name: str = ""
    short_description: str = ""
    type: int | None = None
    contents: int = 0
    description: str | None = None
    values: list[int] = Field(default_factory=list)
    weight: int | None = None
    extra_flags: int | None = None
    timer: int | None = None
    affects: list[LiveItemAffect] = Field(default_factory=list)
    wear_flags: int | None = None
    """Solo `obj.get` (sola lettura)."""
    cost: int | None = None
    cost_per_day: int | None = None
    bitvector: int | None = None


class LiveInventory(AliasedBaseModel):
    """Inventario ed equipaggiamento di un giocatore connesso: elenco piatto in preordine (`depth` per l'annidamento)."""

    name: str
    carry_weight: int = 0
    carry_items: int = 0
    count: int = 0
    truncated: bool = False
    items: list[LiveItem] = Field(default_factory=list)


class LiveItemExpect(AliasedBaseModel):
    """Impronta dell'oggetto letta dal client: obbligatoria in ogni scrittura (altrimenti 409 `worldlive.stale_ref`)."""

    vnum: int | None = None
    fp: str = Field(pattern=r"^[0-9a-f]{8}$")


class LiveItemChanges(AliasedBaseModel):
    """Patch parziale di `obj.set`: solo i campi presenti (1-8). `values`/`affects` hanno `null` per «invariato» (la posizione e' l'indice)."""

    name: str | None = Field(default=None, min_length=1, max_length=127)
    short_description: str | None = Field(default=None, min_length=1, max_length=127)
    description: str | None = Field(default=None, min_length=1, max_length=255)
    values: list[int | None] | None = Field(default=None, min_length=1, max_length=4)
    weight: int | None = None
    extra_flags: int | None = None
    timer: int | None = None
    affects: list[LiveItemAffect | None] | None = Field(default=None, min_length=1, max_length=5)

    @model_validator(mode="after")
    def _not_empty(self) -> "LiveItemChanges":
        """Almeno un campo."""
        if not self.model_fields_set:
            raise ValueError("serve almeno un campo")
        return self


class LiveItemSetIn(AliasedBaseModel):
    """Corpo di `PATCH .../inventory/item`."""

    expect: LiveItemExpect
    set: LiveItemChanges
    save: bool = True


class LiveItemSetOut(AliasedBaseModel):
    """Esito di `obj.set`: `item` dopo la modifica, `fp` nuova (il `ref` resta valido)."""

    name: str
    fp: str = ""
    saved: bool = False
    warnings: list[str] = Field(default_factory=list)
    item: LiveItem | None = None


class LiveItemRemoveOut(AliasedBaseModel):
    """Esito di `obj.remove`: `destroyed` conta gli oggetti di primo livello distrutti (contenitore compreso)."""

    name: str
    removed: bool = True
    destroyed: int = 0
    saved: bool = False
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------------------------------------------------ mixin


class LiveAdapter:
    """Mixin opzionale di un `WorldAdapter` con un canale di controllo live (SDK 1.5). Default: 409 `world.capability_missing`.

    Va dichiarata la capability `supports_live`. I metodi alzano `LiveError` (il router li traduce in `worldlive.*`); `actor` e' l'utente
    dell'editor che causa la richiesta (finisce nell'audit del MUD come informazione dichiarata, non come prova d'identita').
    Le scritture NON sono mai ritentate in automatico: dopo un timeout l'esito e' `outcome_unknown`.
    """

    async def live_status(self) -> LiveStatus:
        """Stato del canale (mai un errore: un canale spento e' `unreachable`)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_who(self) -> LiveWho:
        """Giocatori connessi."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_server_info(self) -> LiveServerInfo:
        """Stato del server (uptime, giocatori, zone)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_zones(self) -> LiveZones:
        """Zone come le vede il gioco."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_player_get(self, name: str) -> LivePlayerState:
        """Valori correnti di un giocatore connesso (`not_found`, `player_not_playing`)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_player_set(self, name: str, change: LivePlayerSetIn, *, actor: str | None = None) -> LivePlayerSetOut:
        """Modifica un giocatore connesso (il router ha gia' controllato `read_only`)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_zone_reset(self, reset: LiveZoneResetIn, *, actor: str | None = None) -> LiveZoneResetOut:
        """Forza il reset di una zona."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_zone_reload(self, reload: LiveZoneReloadIn, *, actor: str | None = None) -> LiveZoneReloadOut:
        """Rilegge dai file una zona e rifa' il reset (comando `zone.reload`, solo se il MUD lo dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_instances(
        self,
        *,
        room_vnum: int | None = None,
        mob_vnum: int | None = None,
        obj_vnum: int | None = None,
        zone_vnum: int | None = None,
        limit: int = 100,
    ) -> LiveInstances:
        """Istanze in memoria per stanza, prototipo o zona (comando `instances.list`, solo se il MUD lo dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_content_validate(self, *, strict: bool = False) -> LiveContentValidateOut:
        """Controlla i file dei contenuti come li carica il gioco (comando `content.validate`, solo se il MUD lo dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_content_reload(self, reload: LiveContentReloadIn, *, actor: str | None = None) -> LiveContentReloadOut:
        """Il gioco rilegge dai file razze, classi, skill, tabelle, social o cataloghi (comando `content.reload`, solo se il MUD lo dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_board_delete(self, board_id: str, message_id: int, *, actor: str | None = None) -> LiveBoardDeleteOut:
        """Toglie un messaggio di bacheca nel gioco (comando `board.delete`, `message_id` e' l'id riga del DB, solo se il MUD lo dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_board_clear(self, board_id: str, *, actor: str | None = None) -> LiveBoardClearOut:
        """Svuota una bacheca nel gioco (comando `board.clear`, solo se il MUD lo dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_load(self, kind: Literal["mob", "obj"], load: LiveLoadIn, *, actor: str | None = None) -> LiveLoadOut:
        """Crea mob o oggetti in una stanza o a un giocatore."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_echo(self, echo: LiveEchoIn, *, actor: str | None = None) -> LiveEchoOut:
        """Manda un messaggio a tutti, a un giocatore o a una stanza."""
        raise api_error(409, "world.capability_missing", capability="supports_live")

    async def live_player_inventory(self, name: str) -> LiveInventory:
        """Inventario ed equipaggiamento di un giocatore connesso (feature `inventory`; `command_disabled` se il MUD non la dichiara)."""
        raise api_error(409, "world.capability_missing", capability="supports_live_inventory")

    async def live_item_get(self, name: str, ref: str) -> LiveItem:
        """Un oggetto istanza (`ref` di `live_player_inventory`; con i campi di sola lettura)."""
        raise api_error(409, "world.capability_missing", capability="supports_live_inventory")

    async def live_item_set(self, name: str, ref: str, change: LiveItemSetIn, *, actor: str | None = None) -> LiveItemSetOut:
        """Modifica un oggetto istanza (`expect` obbligatorio: `stale_ref` se non coincide; mai ritentata)."""
        raise api_error(409, "world.capability_missing", capability="supports_live_inventory")

    async def live_item_remove(
        self, name: str, ref: str, expect: LiveItemExpect, *, save: bool = True, actor: str | None = None
    ) -> LiveItemRemoveOut:
        """Toglie e distrugge un oggetto istanza (e il suo contenuto)."""
        raise api_error(409, "world.capability_missing", capability="supports_live_inventory")


__all__ = [
    "IMMORTAL_LEVEL",
    "LIVE_NAME_RE",
    "LiveAdapter",
    "LiveApplied",
    "LiveEchoIn",
    "LiveEchoOut",
    "LiveError",
    "LiveInstance",
    "LiveInstances",
    "LiveInventory",
    "LiveItem",
    "LiveItemAffect",
    "LiveItemChanges",
    "LiveItemExpect",
    "LiveItemRemoveOut",
    "LiveItemSetIn",
    "LiveItemSetOut",
    "LiveLoadIn",
    "LiveLoadOut",
    "LivePlayerSetIn",
    "LivePlayerSetOut",
    "LivePlayerState",
    "LiveServerInfo",
    "LiveState",
    "LiveStatus",
    "LiveWho",
    "LiveWhoPlayer",
    "LiveZone",
    "LiveContentIssue",
    "LiveBoardClearOut",
    "LiveBoardDeleteOut",
    "LiveContentReloadIn",
    "LiveContentReloadOut",
    "LiveContentValidateOut",
    "LiveZoneReloadIn",
    "LiveZoneReloadOut",
    "LiveZoneResetIn",
    "LiveZoneResetOut",
    "LiveZones",
    "http_error",
    "live_errors",
]
