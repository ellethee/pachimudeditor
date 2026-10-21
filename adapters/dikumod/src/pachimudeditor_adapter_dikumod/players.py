"""Giocatori di Diku Modificato in sola lettura (mixin di `DikumodAdapter`): elenco, dettaglio, inventario/equipaggiamento.

Fonti: `lib/players/<nome>.dat` (un `char_file_u` da 3036 byte per file) e `lib/rent/<nome>` (oggetti). Nessuna scrittura.
La password non esce mai: solo `hasPassword`. Il «server acceso» si rileva (best effort) cercando un processo con cwd = `lib/`
che abbia socket aperti (il server fa `chdir` nella cartella dati); un elenco dei connessi su disco non esiste.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pachifast.i18n import api_error
from pachifast.schemas.responses import PaginatedResponse

from pachimudeditor_adapter_dikumod.base import DikumodSupport
from pachimudeditor_adapter_dikumod.dikumod_lib import tables as T
from pachimudeditor_adapter_dikumod.dikumod_lib.players import (
    CLASS_NAMES,
    CONDITION_NAMES,
    MAX_WEAR,
    NAME_RE,
    CharRecord,
    PlayerFileError,
    RentFile,
    RentItem,
    player_names,
    read_char_file,
    read_rent_file,
)
from pachimudeditor.sdk import (
    ExtraFieldDescriptor,
    PlayerColumn,
    PlayerDetail,
    PlayerInventory,
    PlayerItem,
    PlayerListColumn,
    PlayerListInfo,
    PlayerPageParams,
    PlayersAdapter,
    PlayersInfo,
    PlayersStatus,
    PlayerSummary,
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


def _fx(name: str, kind: Any, group: str, enum: str | None = None) -> ExtraFieldDescriptor:
    """Campo di dettaglio in sola lettura nella sezione `group`; etichetta `playerFiles.field.<name>`."""
    return xf(name, kind, enum, ro=True, nullable=True, group=group).model_copy(update={"label_key": f"playerFiles.field.{name}"})


DETAIL_FIELDS: list[ExtraFieldDescriptor] = [
    _fx("title", "text", "general"), _fx("alias", "text", "general"), _fx("description", "text", "general"),
    _fx("birth", "text", "general"), _fx("weight", "number", "general"), _fx("height", "number", "general"),
    _fx("hometown", "number", "general"), _fx("alignment", "number", "general"), _fx("levels", "json", "general"),
    _fx("startRoom", "number", "general"), _fx("spellsToLearn", "number", "general"), _fx("speaks", "number", "general"),
    _fx("classMask", "number", "general"),
    *(_fx(n, "number", "abilities") for n in ("str", "strAdd", "int", "wis", "dex", "con", "chr")),
    *(_fx(n, "number", "points") for n in ("hit", "maxHit", "mana", "maxMana", "move", "maxMove", "armor", "bankGold", "exp", "hitroll", "damroll")),
    _fx("affectedBy", "flags", "state", "dikumodAffectFlags"), _fx("actFlags", "number", "state"), _fx("userFlags", "number", "state"),
    _fx("conditions", "json", "state"), _fx("savingThrows", "json", "state"), _fx("autoRent", "boolean", "state"),
]  # fmt: skip
"""Campi di `PlayerDetail.details` (sezioni: general, abilities, points, state)."""

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
            rec, mtime = read_char_file(self.players_dir, name)
        except PlayerFileError as error:
            return PlayerSummary(id=name, name=name, problem=error.code), None
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
            "actFlags": rec.act, "userFlags": rec.user_flags,
            "conditions": dict(zip(CONDITION_NAMES, rec.conditions, strict=False)),
            "savingThrows": list(rec.saving_throws), "autoRent": rec.load_room == -2,
        }  # fmt: skip

    # ------------------------------------------------------------------ PlayersAdapter

    def players_info(self) -> PlayersInfo:
        """Colonne, campi e tabelle del dettaglio; il server puo' essere acceso (`online_policy: warn`)."""
        return PlayersInfo(columns=COLUMNS, detail_fields=DETAIL_FIELDS, detail_lists=LISTS, has_accounts=False, online_policy="warn")

    async def players_status(self) -> PlayersStatus:
        """`serverRunning: true` se si trova il server; altrimenti `null` (non si puo' escludere)."""
        running = await asyncio.to_thread(_server_running, self.store.lib)
        return PlayersStatus(server_running=running, detection="proc")

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
        return make_page(PlayerSummary, items, total, params)

    async def get_player(self, player_id: str) -> PlayerDetail:
        """Il dettaglio; un file corrotto restituisce `problem` e nessun dato (mai un 500)."""
        summary, rec = await asyncio.to_thread(self._read_safe, player_id)
        detail = PlayerDetail(**summary.model_dump())
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
            rent = await asyncio.to_thread(read_rent_file, self.rent_dir, player_id)
        except PlayerFileError as error:
            return PlayerInventory(problem=error.code)
        if rent is None:
            return PlayerInventory(extra={"rentFile": False})
        store = self.sync()
        problem = rent.problem
        if problem is None and rent.number and rent.owner.lower() != (rec.name or player_id).lower():
            problem = "owner_mismatch"  # il gioco scarta gli oggetti di un rent con proprietario diverso
        return PlayerInventory(items=[self._item(i, store.objs) for i in rent.items], problem=problem, extra=_rent_extra(rent))

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
