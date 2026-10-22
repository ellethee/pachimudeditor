"""Giocatori di Diku Modificato (mixin di `DikumodAdapter`): elenco, dettaglio, inventario/equipaggiamento, e (SDK 1.4) scrittura.

Fonti: `lib/players/<nome>.dat` (un `char_file_u` da 3036 byte per file) e `lib/rent/<nome>` (oggetti).
La password non esce mai (solo `hasPassword`) e non si scrive mai: il writer (`dikumod_lib/players_write.py`) parte dai byte attuali e
cambia solo i campi richiesti. Ogni scrittura: lock unico, controllo della `revision`, copia nascosta `.<file>.bak` (una generazione, stessi
permessi del file) e poi scrittura atomica (`pachimudeditor.sdk.atomic_write_bytes`). Il «server acceso» si rileva (best effort) cercando un processo con cwd = `lib/`
che abbia socket aperti (il server fa `chdir` nella cartella dati); un elenco dei connessi su disco non esiste.
"""

from __future__ import annotations

import asyncio
import os
import stat
import struct
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pachifast.i18n import api_error, translate
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor_adapter_dikumod.base import DikumodSupport
from pachimudeditor_adapter_dikumod.dikumod_lib import tables as T
from pachimudeditor_adapter_dikumod.store import DikumodStore
from pachimudeditor_adapter_dikumod.dikumod_lib.players import (
    CLASS_NAMES,
    CONDITION_NAMES,
    MAX_WEAR,
    NAME_RE,
    CharRecord,
    PlayerFileError,
    RentFile,
    ITEM_NUMBER_FMT,
    RentItem,
    parse_char_record,
    parse_rent,
    player_names,
    read_char_bytes,
    read_rent_bytes,
    write_target,
)
from pachimudeditor_adapter_dikumod.dikumod_lib.players_write import (
    PlayerValueError,
    RentEditor,
    apply_char_patch,
    char_revision,
    pack_item,
    rent_revision,
    rent_with_gold,
)
from pachimudeditor.sdk import (
    ExtraFieldDescriptor,
    PlayerColumn,
    PlayerDetail,
    PlayerInventory,
    PlayerItem,
    PlayerItemAdd,
    PlayerItemUpdate,
    PlayerListColumn,
    PlayerListInfo,
    PlayerPageParams,
    PlayerPatch,
    PlayersAdapter,
    PlayersInfo,
    PlayersStatus,
    PlayerSummary,
    PlayerWriteOptions,
    atomic_write_bytes,
    make_page,
    paginate_list,
)
from pachimudeditor.sdk import xf


def _pretty(code: str) -> str:
    """`magic_user` -> `Magic user`."""
    return code.replace("_", " ").capitalize()


def _ts(value: float | int) -> datetime | None:
    """Istante UTC di un `time_t`; `None` se zero, negativo o fuori range."""
    try:
        return datetime.fromtimestamp(value, tz=UTC) if value > 0 else None
    except OverflowError, OSError, ValueError:
        return None


def _iso(value: datetime | None) -> str | None:
    """ISO 8601 o `None`."""
    return value.isoformat() if value else None


def _fx(name: str, kind: Any, group: str, enum: str | None = None, *, ro: bool = False) -> ExtraFieldDescriptor:
    """Campo di dettaglio nella sezione `group` (modificabile salvo `ro`); etichetta `playerFiles.field.<name>`."""
    return xf(name, kind, enum, ro=ro, nullable=True, group=group).model_copy(update={"label_key": f"playerFiles.field.{name}"})


DETAIL_FIELDS: list[ExtraFieldDescriptor] = [
    _fx("title", "text", "general"), _fx("alias", "text", "general"), _fx("description", "text", "general"), _fx("extraStr", "text", "general"),
    _fx("birth", "text", "general"), _fx("lastLogon", "text", "general"), _fx("played", "number", "general"),
    _fx("sex", "enum", "general", "dikumodSex"), _fx("race", "enum", "general", "dikumodRace"),
    _fx("weight", "number", "general"), _fx("height", "number", "general"),
    _fx("hometown", "number", "general"), _fx("alignment", "number", "general"), _fx("levels", "json", "general"),
    _fx("loadRoom", "number", "general"), _fx("startRoom", "number", "general"), _fx("spellsToLearn", "number", "general"),
    _fx("speaks", "number", "general"), _fx("classMask", "number", "general"),
    *(_fx(n, "number", "abilities") for n in ("str", "strAdd", "int", "wis", "dex", "con", "chr")),
    *(_fx(n, "number", "points") for n in ("hit", "maxHit", "mana", "maxMana", "move", "maxMove", "armor", "gold", "bankGold", "exp", "trueExp", "hitroll", "damroll")),
    _fx("affectedBy", "flags", "state", "dikumodAffectFlags"), _fx("affectedBy2", "number", "state"), _fx("actFlags", "number", "state"),
    _fx("userFlags", "number", "state"), _fx("extraFlags", "number", "state"),
    _fx("conditions", "json", "state"), _fx("savingThrows", "json", "state"), _fx("autoRent", "boolean", "state", ro=True),
]  # fmt: skip
"""Campi di `PlayerDetail.details` (sezioni: general, abilities, points, state). Tutti modificabili tranne `autoRent` (derivato da `loadRoom`)."""

COLUMNS: list[PlayerColumn] = [
    PlayerColumn(name="name", label_key="playerFiles.col.name", sortable=True),
    PlayerColumn(name="level", label_key="playerFiles.col.level", type="number", sortable=True),
    PlayerColumn(name="classLabel", label_key="playerFiles.col.classLabel", sortable=True),
    PlayerColumn(name="raceLabel", label_key="playerFiles.col.raceLabel", sortable=True),
    PlayerColumn(name="gold", label_key="playerFiles.col.gold", type="number", sortable=True),
    PlayerColumn(name="roomVnum", label_key="playerFiles.col.roomVnum", type="number", sortable=True),
    PlayerColumn(name="lastLoginAt", label_key="playerFiles.col.lastLoginAt", type="datetime", sortable=True),
    PlayerColumn(name="playedSeconds", label_key="playerFiles.col.playedSeconds", type="duration", sortable=True),
    PlayerColumn(name="fileModifiedAt", label_key="playerFiles.col.fileModifiedAt", type="datetime", source="extra"),
    PlayerColumn(name="hasPassword", label_key="playerFiles.col.hasPassword", type="boolean"),
]
LISTS: list[PlayerListInfo] = [
    PlayerListInfo(
        name="skills",
        label_key="playerFiles.list.skills",
        columns=[PlayerListColumn(name=n, label_key=f"playerFiles.list.skill.{n}", type="number") for n in ("index", "learned", "flags", "special", "nummem")],
    ),
    PlayerListInfo(
        name="affects",
        label_key="playerFiles.list.affects",
        columns=[PlayerListColumn(name=n, label_key=f"playerFiles.list.affect.{n}", type="number") for n in ("type", "duration", "modifier", "location", "bitvector")],
    ),
]  # fmt: skip

_AFFECT_NAMES = T.FLAG_TABLES["affect_flags"]
INVENTORY_REASONS = frozenset({"slot_taken", "slot_in_container", "inventory_full", "too_deep", "container_invalid"})
"""Motivi di `PlayerValueError` che sono conflitti con lo stato dell'inventario (409), non valori errati (422)."""


def _server_running(lib: Path) -> bool | None:
    """`True` se un processo ha come cwd `lib` e socket aperti (tipico del server Diku, che fa `chdir` in `lib/`).

    shortcut: solo Linux e solo processi leggibili dall'utente corrente; altrimenti `None` (sconosciuto, mai `False`).
    """
    try:
        target = str(lib.resolve())
        pids = [e for e in os.listdir("/proc") if e.isdigit() and int(e) != os.getpid()]
    except OSError:
        return None
    for pid in pids:
        try:
            if os.readlink(f"/proc/{pid}/cwd") != target:
                continue
            if any(os.readlink(f"/proc/{pid}/fd/{fd}").startswith("socket:") for fd in os.listdir(f"/proc/{pid}/fd")):
                return True
        except OSError:
            continue
    return None


class PlayersMixin(PlayersAdapter, DikumodSupport):
    """Elenco, dettaglio e inventario dei giocatori (vedi docstring del modulo)."""

    @property
    def players_dir(self) -> Path:
        """`lib/players/`."""
        return self.store.lib / "players"

    @property
    def rent_dir(self) -> Path:
        """`lib/rent/`."""
        return self.store.lib / "rent"

    # ------------------------------------------------------------------ mapping

    def _summary(self, name: str) -> tuple[PlayerSummary, CharRecord | None]:
        """Riga dell'elenco per il file `<name>.dat`; se il file e' illeggibile la riga ha `problem` e nessun dato."""
        try:
            data, mtime = read_char_bytes(self.players_dir, name)
        except PlayerFileError as error:
            return PlayerSummary(id=name, name=name, problem=error.code), None
        rec = parse_char_record(data)
        race = _pretty(T.RACES[rec.race]) if 0 <= rec.race < len(T.RACES) else None
        extra: dict[str, Any] = {"fileModifiedAt": _iso(_ts(mtime))}
        if race is None:
            extra["raceRaw"] = rec.race
        summary = PlayerSummary(
            id=name,
            name=rec.name or name,
            level=rec.level,
            class_label=" / ".join(_pretty(c) for c in rec.classes) or None,
            race_label=race,
            sex=T.SEXES[rec.sex] if rec.sex < len(T.SEXES) else None,
            gold=rec.points["gold"],
            room_vnum=rec.load_room if rec.load_room >= 0 else None,
            last_login_at=_ts(rec.last_logon),
            played_seconds=rec.played if rec.played >= 0 else None,
            has_password=rec.has_password,
            revision=char_revision(data),
            extra=extra,
        )
        return summary, rec

    def _details(self, rec: CharRecord) -> dict[str, Any]:
        """Valori dei `DETAIL_FIELDS`."""
        return {
            "title": rec.title, "alias": rec.alias or None, "description": rec.description,
            "birth": _iso(_ts(rec.birth)), "weight": rec.weight, "height": rec.height, "hometown": rec.hometown,
            "alignment": rec.alignment, "classMask": rec.class_mask, "startRoom": rec.start_room,
            "spellsToLearn": rec.spells_to_learn, "speaks": rec.speaks,
            "levels": {_pretty(n): rec.levels[i] for i, n in enumerate(CLASS_NAMES) if rec.levels[i]},
            **{k: v for k, v in rec.abilities.items() if not k.startswith("extra")}, **{k: v for k, v in rec.points.items() if k not in ("gold", "trueExp")},
            "affectedBy": [n for n, bit in _AFFECT_NAMES.items() if rec.affected_by & bit],
            "actFlags": rec.act, "userFlags": rec.user_flags, "extraStr": rec.extra_str or None, "lastLogon": _iso(_ts(rec.last_logon)),
            "played": rec.played, "sex": rec.sex, "race": rec.race, "loadRoom": rec.load_room, "gold": rec.points["gold"],
            "trueExp": rec.points["trueExp"], "extraFlags": rec.extra_flags, "affectedBy2": rec.affected_by2,
            "conditions": dict(zip(CONDITION_NAMES, rec.conditions, strict=False)),
            "savingThrows": list(rec.saving_throws), "autoRent": rec.load_room == -2,
        }  # fmt: skip

    # ------------------------------------------------------------------ PlayersAdapter

    def players_info(self) -> PlayersInfo:
        """Colonne, campi e tabelle del dettaglio; il server puo' essere acceso (`online_policy: warn`)."""
        return PlayersInfo(
            columns=COLUMNS,
            detail_fields=DETAIL_FIELDS,
            detail_lists=LISTS,
            has_accounts=False,
            online_policy="warn",
            wear_slots=list(T.WEAR_POSITIONS),
        )

    async def players_status(self) -> PlayersStatus:
        """`serverRunning: true` se il canale live risponde (certo, `detection: live`) o se si trova il server in `/proc`; altrimenti `null`
        (non si puo' escludere)."""
        if await self.live_reachable():
            return PlayersStatus(server_running=True, detection="live")
        running = await asyncio.to_thread(_server_running, self.store.lib)
        return PlayersStatus(server_running=running, detection="proc")

    async def player_connected(self, player_id: str) -> bool | None:
        """`True` se il canale live mostra il giocatore connesso (anche con il collegamento caduto: il gioco lo ha in memoria e lo salvera'
        sopra il file); altrimenti `None`."""
        return await self.live_online(player_id) or None

    async def _with_online(self, rows: list[PlayerSummary]) -> None:
        """Valorizza `online` (e `extra.liveState`) delle righe col canale live: vero/falso se risponde, invariato altrimenti."""
        players, complete = await self.live_players()
        if players is None:
            return
        for row in rows:
            who = players.get(row.id.lower()) or players.get((row.name or "").lower())
            if who is not None:
                row.online, row.extra["liveState"] = True, who.state
            elif complete:
                row.online = False

    async def list_players(self, params: PlayerPageParams) -> PaginatedResponse[PlayerSummary]:
        """Tutti i `players/*.dat` validi per nome di file, con ricerca per nome e ordinamento."""
        rows = [self._summary(n)[0] for n in await asyncio.to_thread(player_names, self.players_dir)]
        orders = ("id", "name", "level", "class_label", "race_label", "gold", "room_vnum", "last_login_at", "played_seconds")
        items, total = paginate_list(
            rows,
            params,
            lambda p: [p.name, p.id],
            lambda p, f: (getattr(p, f) is None, getattr(p, f)),
            orders,
        )
        await self._with_online(items)
        return make_page(PlayerSummary, items, total, params)

    async def get_player(self, player_id: str) -> PlayerDetail:
        """Il dettaglio; un file corrotto restituisce `problem` e nessun dato (mai un 500)."""
        summary, rec = await asyncio.to_thread(self._read_safe, player_id)
        detail = PlayerDetail(**summary.model_dump())
        await self._with_online([detail])
        if rec is not None:
            detail.details = self._details(rec)
            detail.lists = {
                "skills": [
                    {"index": s.index, "learned": s.learned, "flags": s.flags, "special": s.special, "nummem": s.nummem} for s in rec.skills
                ],
                "affects": [
                    {"type": a.type, "duration": a.duration, "modifier": a.modifier, "location": a.location, "bitvector": a.bitvector}
                    for a in rec.affects
                ],
            }
        return detail

    def _read_safe(self, player_id: str) -> tuple[PlayerSummary, CharRecord | None]:
        """Riga e record. L'id deve essere un nome ammesso (`[a-z][a-z0-9_-]{0,19}`, niente percorsi) e il file deve esistere:
        altrimenti 404 `worldplayers.not_found`."""
        if not NAME_RE.fullmatch(player_id) or not os.path.lexists(self.players_dir / f"{player_id}.dat"):
            raise api_error(404, "worldplayers.not_found")
        return self._summary(player_id)

    async def player_inventory(self, player_id: str) -> PlayerInventory:
        """Oggetti di `rent/<nome>`; i nomi dei prototipi dal mondo; file assente = inventario vuoto."""
        summary, rec = await asyncio.to_thread(self._read_safe, player_id)
        if rec is None:
            return PlayerInventory(problem=summary.problem)
        try:
            data = await asyncio.to_thread(read_rent_bytes, self.rent_dir, player_id)
        except PlayerFileError as error:
            return PlayerInventory(problem=error.code)
        if data is None:
            return PlayerInventory(revision=rent_revision(None), extra={"rentFile": False})
        rent = parse_rent(data, unsigned=self.rent_unsigned)
        store = self.sync()
        problem = rent.problem
        if problem is None and rent.number and rent.owner.lower() != (rec.name or player_id).lower():
            problem = "owner_mismatch"  # il gioco scarta gli oggetti di un rent con proprietario diverso
        return PlayerInventory(
            items=[self._item(i, store.objs) for i in rent.items], problem=problem, revision=rent_revision(data), extra=_rent_extra(rent)
        )

    # ------------------------------------------------------------------ scrittura (SDK 1.4)

    @asynccontextmanager
    async def _writing_players(self) -> AsyncIterator[DikumodStore]:
        """Sezione di scrittura sui file giocatore: mondo non `read_only`, lock unico, archivio riallineato (per i prototipi)."""
        self.ensure_writable()
        async with self.lock:
            yield self.sync()

    def _char_for_write(self, player_id: str, revision: str | None) -> tuple[Path, bytes]:
        """`(percorso reale, byte)` del file giocatore pronto per la scrittura: 404 se manca, 409 `worldplayers.file_unwritable`
        se non e' un file giocatore valido, 409 `worldplayers.conflict` se la `revision` non e' piu' quella attuale."""
        if not NAME_RE.fullmatch(player_id) or not os.path.lexists(self.players_dir / f"{player_id}.dat"):
            raise api_error(404, "worldplayers.not_found")
        try:
            target = write_target(self.players_dir, f"{player_id}.dat")
            data, _ = read_char_bytes(self.players_dir, player_id)
        except PlayerFileError as error:
            raise api_error(409, "worldplayers.file_unwritable", problem=error.code) from error
        if revision is not None and revision != char_revision(data):
            raise api_error(409, "worldplayers.conflict")
        return target, data

    @staticmethod
    def _save(target: Path, new: bytes, old: bytes | None) -> None:
        """Copia `<file>.bak` del contenuto attuale (una sola generazione, stessi permessi del file: il giocatore ha l'hash della
        password) e poi scrittura atomica. `old` nullo = il file non esiste ancora: nessuna copia."""
        if old is not None:
            bak = target.with_name(f".{target.name}.bak")  # nascosto: il gioco salta i file che iniziano con "."
            if bak.is_symlink():
                bak.unlink()
            if not bak.exists():
                mode = stat.S_IMODE(target.stat().st_mode)
                os.close(os.open(bak, os.O_WRONLY | os.O_CREAT, mode))
                os.chmod(bak, mode)
            atomic_write_bytes(bak, old)
        atomic_write_bytes(target, new)

    @staticmethod
    def _value_error(error: PlayerValueError) -> HTTPException:
        """422 `worldplayers.invalid_value` (campo, motivo, limiti); gli errori di stato dell'inventario sono 404/409."""
        if error.reason == "not_found":
            return api_error(404, "worldplayers.item_not_found")
        if error.reason in INVENTORY_REASONS:
            return api_error(409, "worldplayers.item_invalid", reason=error.reason, **error.params)
        hint_code = "worldplayers.hint.vnum_range" if (error.field, error.reason) == ("vnum", "range") else ""
        hint = translate(hint_code, error.params) if hint_code else ""  # testo aggiuntivo localizzato (vuoto per gli altri errori)
        return api_error(422, "worldplayers.invalid_value", field=error.field, reason=error.reason, hint=hint, **error.params)

    async def update_player(self, player_id: str, patch: PlayerPatch) -> PlayerDetail:
        """Modifica i campi e le tabelle; l'oro cambiato si riporta anche in `gold_left` del rent (il gioco lo confronta col costo
        giornaliero al boot). Password e nome non sono modificabili."""
        async with self._writing_players():
            await asyncio.to_thread(self._update_player_sync, player_id, patch)
        return await self.get_player(player_id)

    def _update_player_sync(self, player_id: str, patch: PlayerPatch) -> None:
        """Parte bloccante di `update_player`."""
        target, data = self._char_for_write(player_id, patch.revision)
        try:
            new = apply_char_patch(data, patch.details, patch.lists)
        except PlayerValueError as error:
            raise self._value_error(error) from error
        if new == data:
            return
        self._save(target, new, data)
        if "gold" in patch.details:
            self._sync_rent_gold(player_id, parse_char_record(new))

    def _sync_rent_gold(self, player_id: str, rec: CharRecord) -> None:
        """Allinea `gold_left` del rent all'oro del personaggio (solo se il rent esiste, e' coerente e del proprietario giusto)."""
        try:
            old = read_rent_bytes(self.rent_dir, player_id)
            updated = rent_with_gold(old, rec.name, rec.points["gold"]) if old else None
            if old and updated and updated != old:
                self._save(write_target(self.rent_dir, player_id), updated, old)
        except PlayerFileError:
            return  # rent illeggibile o fuori cartella: non si tocca

    def _rent_for_write(self, player_id: str, revision: str | None) -> tuple[Path, bytes | None, RentEditor]:
        """`(percorso, byte attuali o None, editor)` del rent di un giocatore; stessi errori di `_char_for_write`
        (409 `worldplayers.file_unwritable` col codice di problema del rent)."""
        _, char_data = self._char_for_write(player_id, None)
        rec = parse_char_record(char_data)
        try:
            target = write_target(self.rent_dir, player_id)
            data = read_rent_bytes(self.rent_dir, player_id)
            if revision is not None and revision != rent_revision(data):
                raise api_error(409, "worldplayers.conflict")
            editor = RentEditor(data, rec.name, gold=rec.points["gold"], now=int(time.time()), unsigned=self.rent_unsigned)
        except PlayerFileError as error:
            raise api_error(409, "worldplayers.file_unwritable", problem=error.code) from error
        except PlayerValueError as error:
            raise api_error(409, "worldplayers.file_unwritable", problem=error.reason) from error
        return target, data, editor

    @staticmethod
    def _wearpos(slot: str | None) -> int:
        """Numero di slot (`wearpos`) di un nome di `PlayersInfo.wear_slots`; `None` = 0 (portato)."""
        if slot is None:
            return 0
        if slot not in T.WEAR_POSITIONS:
            raise PlayerValueError("wearSlot", "enum")
        return T.WEAR_POSITIONS.index(slot) + 1

    def _rent_of(self, store: DikumodStore, vnum: int) -> int:
        """Costo giornaliero (rent) del prototipo `vnum`, 0 se ignoto o negativo."""
        ref = store.objs.get(vnum)
        return max(ref.item.rent, 0) if ref is not None else 0

    async def add_player_item(self, player_id: str, item: PlayerItemAdd) -> PlayerInventory:
        """Aggiunge un oggetto creato dal prototipo (valori, flag, peso, nomi, effetti; `timer`/`bitvector` a 0)."""
        async with self._writing_players() as store:
            await asyncio.to_thread(self._add_item_sync, player_id, item, store)
        return await self.player_inventory(player_id)

    def _add_item_sync(self, player_id: str, item: PlayerItemAdd, store: DikumodStore) -> None:
        """Parte bloccante di `add_player_item`."""
        ref = store.objs.get(item.vnum)
        if ref is None:
            raise api_error(404, "worldplayers.unknown_object", vnum=item.vnum)
        target, data, editor = self._rent_for_write(player_id, item.revision)
        proto = ref.item
        try:
            if item.container_id is not None:
                if not 0 <= item.container_id < len(editor.records):
                    raise PlayerValueError("item", "not_found")
                (parent_vnum,) = struct.unpack_from(ITEM_NUMBER_FMT[self.rent_unsigned], editor.records[item.container_id], 0)
                parent = store.objs.get(parent_vnum)
                if parent is None or parent.item.type != T.ITEM_TYPES.index("container"):
                    raise PlayerValueError("item", "container_invalid")  # il gioco ignora i prototipi ignoti: i figli resterebbero orfani
            element = pack_item(
                item.vnum, values=proto.values, extra_flags=proto.extra_flags, weight=proto.weight, name=proto.name, short=proto.short,
                description=proto.description, affects=[(a.location, a.modifier) for a in proto.affects], unsigned=self.rent_unsigned,
            )  # fmt: skip
            editor.add(element, self._wearpos(item.wear_slot), item.container_id)
        except PlayerValueError as error:
            raise self._value_error(error) from error
        editor.total_cost += self._rent_of(store, item.vnum)
        self._save(target, editor.to_bytes(), data)

    async def update_player_item(self, player_id: str, item_id: int, change: PlayerItemUpdate) -> PlayerInventory:
        """Cambia lo slot di un oggetto di primo livello."""
        async with self._writing_players() as store:
            await asyncio.to_thread(self._update_item_sync, player_id, item_id, change, store)
        return await self.player_inventory(player_id)

    def _update_item_sync(self, player_id: str, item_id: int, change: PlayerItemUpdate, store: DikumodStore) -> None:
        """Parte bloccante di `update_player_item`."""
        target, data, editor = self._rent_for_write(player_id, change.revision)
        try:
            editor.set_wearpos(item_id, self._wearpos(change.wear_slot))
        except PlayerValueError as error:
            raise self._value_error(error) from error
        self._save(target, editor.to_bytes(), data)

    async def remove_player_item(self, player_id: str, item_id: int, options: PlayerWriteOptions) -> PlayerInventory:
        """Toglie l'oggetto con il suo contenuto e ne sottrae il costo giornaliero da `total_cost`."""
        async with self._writing_players() as store:
            await asyncio.to_thread(self._remove_item_sync, player_id, item_id, options, store)
        return await self.player_inventory(player_id)

    def _remove_item_sync(self, player_id: str, item_id: int, options: PlayerWriteOptions, store: DikumodStore) -> None:
        """Parte bloccante di `remove_player_item`."""
        target, data, editor = self._rent_for_write(player_id, options.revision)
        try:
            removed = editor.delete(item_id)
        except PlayerValueError as error:
            raise self._value_error(error) from error
        editor.total_cost = max(
            0,
            editor.total_cost
            - sum(self._rent_of(store, struct.unpack_from(ITEM_NUMBER_FMT[self.rent_unsigned], r, 0)[0]) for r in removed),
        )
        self._save(target, editor.to_bytes(), data)

    @staticmethod
    def _item(item: RentItem, protos: dict[int, Any]) -> PlayerItem:
        """DTO di un oggetto salvato; `known` se il prototipo (vnum) esiste nel mondo."""
        proto = protos.get(item.item_number)
        slot = None
        extra: dict[str, Any] = {
            "values": list(item.values), "extraFlags": item.extra_flags, "weight": item.weight, "timer": item.timer,
            "affects": [{"location": a.location, "modifier": a.modifier} for a in item.affects],
        }  # fmt: skip
        if item.wearpos:
            slot = (
                T.WEAR_POSITIONS[item.wearpos - 1]
                if item.wearpos <= MAX_WEAR and item.wearpos <= len(T.WEAR_POSITIONS)
                else f"slot_{item.wearpos}"
            )
        if proto is not None:
            obj = proto.item
            extra["itemType"] = T.ITEM_TYPES[obj.type] if 0 <= obj.type < len(T.ITEM_TYPES) else obj.type
            extra["prototypeShort"] = obj.short
        return PlayerItem(
            id=item.index,
            vnum=item.item_number,
            name=item.short or (proto.item.short if proto is not None else ""),
            keywords=item.name or (proto.item.name if proto is not None else ""),
            wear_slot=slot,
            depth=item.depth,
            known=proto is not None,
            extra=extra,
        )


def _rent_extra(rent: RentFile) -> dict[str, Any]:
    """Dati di testata del file rent (senza gli oggetti)."""
    return {
        "rentFile": True, "goldLeft": rent.gold_left, "totalCost": rent.total_cost, "lastUpdate": _iso(_ts(rent.last_update)),
        "minimumStay": rent.minimum_stay, "declaredNumber": rent.number,
    }  # fmt: skip
