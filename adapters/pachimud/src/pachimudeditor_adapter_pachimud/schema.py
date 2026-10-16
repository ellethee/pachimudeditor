"""Schema del database di pachimud letto "al volo" (schema-on-read): riflessione delle tabelle reali.

L'editor NON importa i modelli ORM del gioco. All'apertura del mondo si leggono con `MetaData.reflect` le tabelle
`zone`, `room`, `exit`, ... del database vero e su di esse si mappano (mapping imperativo, senza relazioni) classi
minime con gli stessi nomi dei modelli del gioco (`Zone`, `Room`, ...). Il significato delle colonne intere (enum)
sta nelle tabelle dati di `common/enums.py`.

Compatibilita' con il gioco:

- `REVISIONS` elenca le revisioni alembic note (in ordine) e `EXPECTED` le colonne attese di ogni tabella, con la
  revisione che le ha introdotte;
- il controllo (`SchemaReport`) legge `alembic_version` e confronta: revisione ignota, colonne attese assenti o
  colonne NOT NULL sconosciute senza default danno *avvisi*, mai un errore;
- una colonna assente ma non essenziale (es. `race_id`, `arg_str`, `heal_rate`) e' "non supportata": in lettura vale
  il valore neutro, in scrittura e' accettato solo quello (422 `world.field_unsupported`) e `describe()` la marca
  `unsupported`; una tabella opzionale assente (`account`, `mob_instance`, ...) spegne la capability collegata;
- mancano tabelle o colonne essenziali (chiavi, vnum): il mondo e' "incompatibile" (503 `world.unavailable`).
"""

import asyncio
import concurrent.futures
import copy
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal

from pachifast.i18n import api_error
from sqlalchemy import MetaData, Table, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import registry

log = logging.getLogger(__name__)

REVISIONS: tuple[str, ...] = ("64f2026e1334", "f8c896cb5dd8", "848330e8786f", "9d4aa2f29079")
"""Revisioni alembic del gioco note, dalla piu' vecchia (`alembic/versions` del repo pachimud)."""

REVISION_NOTES: dict[str, str] = {
    "64f2026e1334": "schema iniziale",
    "f8c896cb5dd8": "livelli di zona, heal/mana rate, clan e owner delle stanze",
    "848330e8786f": "zone_reset_command.arg_str",
    "9d4aa2f29079": "mob_prototype.race_id e class_id",
}
HEAD = REVISIONS[-1]
"""L'ultima revisione nota."""


# ------------------------------------------------------------------------------ colonne attese

_NO_DEFAULT: Any = object()


@dataclass(frozen=True)
class Col:
    """Una colonna attesa: tipo logico, nullabilita', revisione di introduzione e default Python all'inserimento."""

    kind: Literal["int", "bool", "str", "list", "dict", "datetime"]
    null: bool = False
    essential: bool = False
    """Senza questa colonna la tabella non e' utilizzabile (chiavi, vnum): niente valore neutro."""
    since: int = 0
    """Indice in `REVISIONS` della revisione che la introduce."""
    default: Any = _NO_DEFAULT
    """Come `default=` del modello del gioco (valore o callable), applicato se l'inserimento non la indica."""

    @property
    def neutral(self) -> Any:
        """Il valore neutro per una colonna assente."""
        if self.null:
            return None
        if self.default is not _NO_DEFAULT and not callable(self.default):
            return self.default  # es. heal_rate 100, min_level 1: il valore che il gioco darebbe di default
        return {"int": 0, "bool": False, "str": "", "list": [], "dict": {}, "datetime": None}[self.kind]


def _c(kind: str, **kw: Any) -> Col:
    """Abbreviazione di `Col`."""
    return Col(kind, **kw)  # type: ignore[arg-type]


_ID = _c("int", essential=True)


def _now() -> datetime:
    """`datetime.now(UTC)`: default di `created_at` come nel gioco."""
    return datetime.now(UTC)


EXPECTED: dict[str, dict[str, Col]] = {
    "zone": {
        "id": _ID,
        "vnum": _c("int", essential=True),
        "name": _c("str"),
        "builder": _c("str"),
        "bottom_vnum": _c("int"),
        "top_vnum": _c("int"),
        "min_level": _c("int", since=1, default=1),
        "max_level": _c("int", since=1, default=1),
        "lifespan_minutes": _c("int"),
        "reset_mode": _c("int"),
        "enabled": _c("bool", default=True),
    },
    "room": {
        "id": _ID,
        "vnum": _c("int", essential=True),
        "zone_id": _c("int", essential=True),
        "name": _c("str"),
        "description": _c("str"),
        "sector_type": _c("int"),
        "flags": _c("list", default=list),
        "heal_rate": _c("int", since=1, default=100),
        "mana_rate": _c("int", since=1, default=100),
        "clan_id": _c("str", null=True, since=1),
        "owner": _c("str", null=True, since=1),
    },
    "exit": {
        "id": _ID,
        "room_id": _c("int", essential=True),
        "direction": _c("int", essential=True),
        "description": _c("str", null=True),
        "keywords": _c("str", null=True),
        "door_flag": _c("int", default=0),
        "is_open": _c("bool", default=True),
        "is_locked": _c("bool", default=False),
        "key_vnum": _c("int", null=True),
        "target_room_id": _c("int", null=True),
    },
    "room_extra_description": {
        "id": _ID,
        "room_id": _c("int", essential=True),
        "keywords": _c("str"),
        "text": _c("str"),
    },
    "mob_prototype": {
        "id": _ID,
        "vnum": _c("int", essential=True),
        "zone_id": _c("int", essential=True),
        "keywords": _c("str"),
        "short_description": _c("str"),
        "long_description": _c("str"),
        "detailed_description": _c("str"),
        "level": _c("int"),
        "thac0": _c("int"),
        "armor_class": _c("int"),
        "hp_dice_count": _c("int"),
        "hp_die_size": _c("int"),
        "hp_bonus": _c("int"),
        "damage_dice_count": _c("int"),
        "damage_die_size": _c("int"),
        "damage_bonus": _c("int"),
        "gold": _c("int"),
        "experience": _c("int"),
        "sex": _c("int"),
        "flags": _c("list", default=list),
        "debuff_skill_id": _c("str", null=True),
        "alignment": _c("int", default=0),
        "shop_id": _c("str", null=True),
        "quest_ids": _c("list", default=list),
        "is_banker": _c("bool", default=False),
        "teaches_class_ids": _c("list", null=True),
        "teaches_skill_ids": _c("list", null=True),
        "race_id": _c("str", null=True, since=3),
        "class_id": _c("str", null=True, since=3),
    },
    "object_prototype": {
        "id": _ID,
        "vnum": _c("int", essential=True),
        "zone_id": _c("int", essential=True),
        "keywords": _c("str"),
        "short_description": _c("str"),
        "long_description": _c("str"),
        "action_description": _c("str", null=True),
        "object_type": _c("int"),
        "weight": _c("int"),
        "cost": _c("int"),
        "rent": _c("int"),
        "value_0": _c("int", null=True),
        "value_1": _c("int", null=True),
        "value_2": _c("int", null=True),
        "value_3": _c("int", null=True),
        "extra_flags": _c("list", default=list),
        "wear_flags": _c("list", default=list),
        "affects": _c("dict", default=dict),
    },
    "zone_reset_command": {
        "id": _ID,
        "zone_id": _c("int", essential=True),
        "order_index": _c("int", essential=True),
        "command_type": _c("int", essential=True),
        "if_flag": _c("bool", default=False),
        "arg1": _c("int", null=True),
        "arg2": _c("int", null=True),
        "arg3": _c("int", null=True),
        "arg4": _c("int", null=True),
        "arg_str": _c("str", null=True, since=2),
    },
    "mob_instance": {
        "id": _ID,
        "prototype_id": _c("int", essential=True),
        "room_id": _c("int", essential=True),
        "hit_points_current": _c("int"),
        "hit_points_max": _c("int"),
        "gold": _c("int", null=True),
        "master_character_id": _c("int", null=True),
        "charmed_until": _c("datetime", null=True),
    },
    "object_instance": {
        "id": _ID,
        "prototype_id": _c("int", essential=True),
        "room_id": _c("int", null=True),
        "character_id": _c("int", null=True),
        "container_instance_id": _c("int", null=True),
        "mob_instance_id": _c("int", null=True),
        "equipped_slot": _c("str", null=True),
        "liquid_amount": _c("int", null=True),
        "charges": _c("int", null=True),
        "liquid_type": _c("int", null=True),
        "liquid_poisoned": _c("bool", null=True),
    },
    "account": {
        "id": _ID,
        "username": _c("str", essential=True),
        "password_hash": _c("str", essential=True),
        "email": _c("str", null=True),
        "created_at": _c("datetime", default=_now),
        "last_login_at": _c("datetime", null=True),
        "is_banned": _c("bool", default=False),
    },
    "player_character": {
        "id": _ID,
        "account_id": _c("int", essential=True),
        "name": _c("str", essential=True),
        "level": _c("int", default=1),
        "experience": _c("int", default=0),
        "hit_points_current": _c("int"),
        "hit_points_max": _c("int"),
        "gold": _c("int", default=0),
        "current_room_id": _c("int", null=True),
        "sex": _c("int"),
        "class_id": _c("str"),
        "race_id": _c("str"),
        "strength": _c("int"),
        "strength_percentile": _c("int", default=0),
        "dexterity": _c("int"),
        "constitution": _c("int"),
        "intelligence": _c("int"),
        "wisdom": _c("int"),
        "charisma": _c("int"),
        "mana_current": _c("int"),
        "mana_max": _c("int"),
        "known_skill_ids": _c("list", default=list),
        "practices": _c("int", default=0),
        "skill_percentages": _c("dict", default=dict),
        "alignment": _c("int", default=0),
        "preferences": _c("list", default=list),
        "position": _c("str", default="STANDING"),
        "hunger": _c("int", default=24),
        "thirst": _c("int", default=24),
        "drunk": _c("int", default=0),
        "poison_ticks": _c("int", default=0),
        "wimpy_level": _c("int", default=0),
        "is_player_killer": _c("bool", default=False),
        "title": _c("str", default=""),
        "active_quest_ids": _c("list", default=list),
        "completed_quest_ids": _c("list", default=list),
        "quest_progress": _c("dict", default=dict),
        "quest_points": _c("int", default=0),
        "bank_gold": _c("int", default=0),
        "created_at": _c("datetime", default=_now),
        "last_played_at": _c("datetime", null=True),
    },
}
"""Tabella -> colonna -> specifica, per la revisione `HEAD`."""

CORE_TABLES: tuple[str, ...] = (
    "zone",
    "room",
    "exit",
    "mob_prototype",
    "object_prototype",
    "zone_reset_command",
)
"""Senza una di queste il mondo non e' utilizzabile."""

OPTIONAL_TABLES: dict[str, str] = {
    "room_extra_description": "supports_extra_descriptions",
    "mob_instance": "supports_instances",
    "object_instance": "supports_instances",
    "account": "supports_players",
    "player_character": "supports_players",
}
"""Tabella opzionale -> capability che spegne se manca."""

CLASS_NAMES: dict[str, str] = {
    "zone": "Zone",
    "room": "Room",
    "exit": "Exit",
    "room_extra_description": "RoomExtraDescription",
    "mob_prototype": "MobPrototype",
    "object_prototype": "ObjectPrototype",
    "zone_reset_command": "ZoneResetCommand",
    "mob_instance": "MobInstance",
    "object_instance": "ObjectInstance",
    "account": "Account",
    "player_character": "PlayerCharacter",
}
"""Tabella -> nome della classe mappata (gli stessi nomi dei modelli del gioco)."""

RESOURCE_OF_TABLE: dict[str, str] = {
    "zone": "zone",
    "room": "room",
    "exit": "exit",
    "room_extra_description": "extra_description",
    "mob_prototype": "mob",
    "object_prototype": "object",
    "zone_reset_command": "reset_command",
}
"""Tabella -> tipo di risorsa di `describe()` (per marcare i campi non supportati)."""


# ------------------------------------------------------------------------------ righe mappate


class _Neutral:
    """Attributo di una colonna assente: restituisce (una copia del) valore neutro."""

    def __init__(self, value: Any) -> None:
        """Memorizza il valore neutro."""
        self.value = value

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        """Il valore neutro (copia, per liste e dict)."""
        return copy.copy(self.value)

    def __set__(self, instance: Any, value: Any) -> None:
        """Le scritture su una colonna assente sono ignorate (le blocca prima `strip_unsupported`)."""


class GameRow:
    """Base delle classi mappate: costruttore a parole chiave con i default Python del gioco."""

    __table__: ClassVar[Table]
    __unsupported__: ClassVar[dict[str, Any]] = {}
    """Colonne attese ma assenti nel DB -> valore neutro."""

    def __init__(self, **values: Any) -> None:
        """Valorizza le colonne indicate e, per le altre, il default Python previsto (liste vuote, `True`, ...)."""
        table = type(self).__table__
        for name, value in values.items():
            if name in table.c:
                setattr(self, name, value)
        for name, spec in EXPECTED.get(table.name, {}).items():
            if name in table.c and name not in values and spec.default is not _NO_DEFAULT:
                setattr(self, name, spec.default() if callable(spec.default) else spec.default)

    def __repr__(self) -> str:
        """`Zone(id=1)`."""
        return f"{type(self).__name__}(id={getattr(self, 'id', None)!r})"


def strip_unsupported(model: type, values: Mapping[str, Any]) -> dict[str, Any]:
    """`values` senza le chiavi delle colonne assenti dal DB.

    Raises:
        HTTPException: 422 `world.field_unsupported` se il valore di una colonna assente non e' quello neutro.
    """
    unsupported: dict[str, Any] = getattr(model, "__unsupported__", {})
    out: dict[str, Any] = {}
    for name, value in values.items():
        if name in unsupported:
            if value != unsupported[name]:
                raise api_error(422, "world.field_unsupported", field=_camel(name))
            continue
        out[name] = value
    return out


def _camel(name: str) -> str:
    """`heal_rate` -> `healRate`."""
    head, *rest = name.split("_")
    return head + "".join(part.capitalize() for part in rest)


class GameModels:
    """Le classi mappate di un database di gioco (una per tabella presente) e le informazioni sul suo schema."""

    Zone: type[GameRow]
    Room: type[GameRow]
    Exit: type[GameRow]
    RoomExtraDescription: type[GameRow] | None
    MobPrototype: type[GameRow]
    ObjectPrototype: type[GameRow]
    ZoneResetCommand: type[GameRow]
    MobInstance: type[GameRow] | None
    ObjectInstance: type[GameRow] | None
    Account: type[GameRow] | None
    PlayerCharacter: type[GameRow] | None

    def __init__(self, tables: Mapping[str, Table], unsupported: Mapping[str, dict[str, Any]]) -> None:
        """Mappa ogni tabella presente su una classe; le assenti (opzionali) valgono `None`."""
        reg = registry()
        self.tables = dict(tables)
        self.unsupported = {name: dict(cols) for name, cols in unsupported.items()}
        for table_name, class_name in CLASS_NAMES.items():
            table = tables.get(table_name)
            if table is None:
                setattr(self, class_name, None)
                continue
            attrs: dict[str, Any] = {"__unsupported__": self.unsupported.get(table_name, {})}
            for column, neutral in attrs["__unsupported__"].items():
                attrs[column] = _Neutral(neutral)
            cls = type(class_name, (GameRow,), attrs)
            reg.map_imperatively(cls, table)
            cls.__table__ = table
            setattr(self, class_name, cls)

    def has(self, table: str) -> bool:
        """`True` se la tabella esiste nel DB."""
        return table in self.tables

    def column(self, table: str, name: str) -> bool:
        """`True` se la colonna esiste nel DB."""
        return table in self.tables and name in self.tables[table].c

    def unsupported_fields(self, resource: str) -> frozenset[str]:
        """I campi (camelCase) di una risorsa di `describe()` senza colonna nel DB."""
        out: set[str] = set()
        for table, resource_type in RESOURCE_OF_TABLE.items():
            if resource_type == resource:
                out |= {_camel(c) for c in self.unsupported.get(table, {})}
        return frozenset(out)


def models_of(session: AsyncSession) -> GameModels:
    """Le classi mappate del mondo a cui appartiene la sessione (impostate da `PachimudAdapter.session`)."""
    return session.info["models"]  # type: ignore[no-any-return]


# ------------------------------------------------------------------------------ controllo dello schema


@dataclass
class SchemaIssue:
    """Un rilievo del controllo di schema."""

    severity: Literal["info", "warning", "error"]
    code: str
    message: str


SchemaStatus = Literal["ok", "behind", "unknown", "unversioned", "incompatible"]


@dataclass
class SchemaReport:
    """Esito del confronto tra lo schema letto e le revisioni note del gioco."""

    revision: str | None
    status: SchemaStatus
    issues: list[SchemaIssue] = field(default_factory=list)
    unsupported: dict[str, list[str]] = field(default_factory=dict)
    """Tabella -> colonne attese ma assenti (funzioni degradate)."""
    missing_tables: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """`False` se mancano tabelle o colonne essenziali."""
        return self.status != "incompatible"

    @property
    def warnings(self) -> list[SchemaIssue]:
        """Avvisi ed errori (non le semplici informazioni)."""
        return [i for i in self.issues if i.severity != "info"]

    def summary(self) -> str:
        """Una riga per `worlds check`: `rev 9d4aa2f29079 (ok)`, `rev sconosciuta xyz: 2 avvisi`, ..."""
        rev = self.revision or "nessuna"
        extra = f", {len(self.warnings)} avvisi" if self.warnings else ""
        return f"schema {self.status}, revisione {rev}{extra}"


def check_schema(tables: Mapping[str, Table], revision: str | None) -> tuple[SchemaReport, dict[str, dict[str, Any]]]:
    """Confronta le tabelle riflesse con quelle attese. Restituisce il rapporto e le colonne non supportate
    (tabella -> colonna -> valore neutro)."""
    issues: list[SchemaIssue] = []
    unsupported: dict[str, dict[str, Any]] = {}
    missing_tables: list[str] = []
    fatal = False
    known = revision in REVISIONS
    rank = REVISIONS.index(revision) if known else len(REVISIONS) - 1  # revisione ignota: ci si aspetta la piu' recente nota

    if revision is None:
        issues.append(SchemaIssue("warning", "unversioned", "tabella alembic_version assente o vuota: revisione non verificabile"))
        status: SchemaStatus = "unversioned"
    elif not known:
        issues.append(
            SchemaIssue(
                "warning",
                "unknown_revision",
                f"revisione alembic sconosciuta {revision!r} (note: {', '.join(REVISIONS)}): "
                f"lo schema potrebbe essere piu' recente dell'editor",
            )
        )
        status = "unknown"
    elif rank < len(REVISIONS) - 1:
        issues.append(
            SchemaIssue("info", "behind", f"revisione {revision} piu' vecchia della piu' recente nota ({HEAD}): funzioni ridotte")
        )
        status = "behind"
    else:
        status = "ok"

    for table_name, columns in EXPECTED.items():
        table = tables.get(table_name)
        if table is None:
            missing_tables.append(table_name)
            if table_name in CORE_TABLES:
                fatal = True
                issues.append(SchemaIssue("error", "missing_table", f"tabella obbligatoria assente: {table_name}"))
            else:
                issues.append(
                    SchemaIssue(
                        "warning", "missing_table", f"tabella opzionale assente: {table_name} ({OPTIONAL_TABLES[table_name]} disattivata)"
                    )
                )
            continue
        for name, spec in columns.items():
            if name in table.c:
                continue
            if spec.essential:
                fatal = True
                issues.append(SchemaIssue("error", "missing_column", f"{table_name}.{name}: colonna essenziale assente"))
                continue
            unsupported.setdefault(table_name, {})[name] = spec.neutral
            late = known and spec.since > rank  # colonna introdotta da una revisione successiva a quella del DB: attesa
            note = f"introdotta dalla revisione {REVISIONS[spec.since]}" if late else "attesa ma assente"
            issues.append(
                SchemaIssue("info" if late else "warning", "missing_column", f"{table_name}.{name}: {note}: campo non supportato")
            )
        for column in table.c:
            if column.name not in columns and not column.nullable and column.server_default is None and not column.primary_key:
                issues.append(
                    SchemaIssue(
                        "warning",
                        "unknown_required_column",
                        f"{table_name}.{column.name}: colonna NOT NULL sconosciuta senza default: gli inserimenti potrebbero fallire",
                    )
                )
            elif column.name not in columns:
                issues.append(SchemaIssue("info", "unknown_column", f"{table_name}.{column.name}: colonna sconosciuta (ignorata)"))
    if fatal:
        status = "incompatible"
    report = SchemaReport(
        revision=revision,
        status=status,
        issues=issues,
        unsupported={t: sorted(c) for t, c in unsupported.items()},
        missing_tables=missing_tables,
    )
    return report, unsupported


# ------------------------------------------------------------------------------ caricamento


class SchemaUnavailable(Exception):
    """Il database non e' raggiungibile o non e' uno schema di gioco utilizzabile (messaggio per l'utente)."""

    def __init__(self, message: str, report: "SchemaReport | None" = None) -> None:
        """`report` e' presente quando il DB e' stato letto ma lo schema e' incompatibile."""
        super().__init__(message)
        self.report = report


@dataclass
class GameSchema:
    """Schema riflesso di un mondo: classi mappate e rapporto di compatibilita'."""

    models: GameModels
    report: SchemaReport


async def _reflect(url: str) -> tuple[MetaData, str | None]:
    """Legge con un engine temporaneo le tabelle note e la revisione alembic."""
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            names = set(await conn.run_sync(lambda c: inspect(c).get_table_names()))
            wanted = [n for n in (*EXPECTED, "alembic_version") if n in names]
            metadata = MetaData()
            await conn.run_sync(lambda c: metadata.reflect(c, only=wanted))
            revision: str | None = None
            if "alembic_version" in names:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
                revision = str(row[0]) if row else None
    except Exception as exc:  # noqa: BLE001 - qualunque errore di connessione/lettura
        raise SchemaUnavailable(f"{type(exc).__name__}: {exc}") from exc
    finally:
        await engine.dispose()
    return metadata, revision


def load_schema(url: str) -> GameSchema:
    """Riflette il database e costruisce le classi mappate (sincrono: gira in un thread con un loop proprio).

    Raises:
        SchemaUnavailable: database non raggiungibile oppure schema incompatibile (mancano tabelle/colonne essenziali).
    """

    def run() -> tuple[MetaData, str | None]:
        """Esegue la riflessione in un event loop dedicato."""
        return asyncio.run(_reflect(url))

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        metadata, revision = pool.submit(run).result()
    report, unsupported = check_schema(metadata.tables, revision)
    if not report.usable:
        problems = "; ".join(i.message for i in report.issues if i.severity == "error")
        raise SchemaUnavailable(f"schema di gioco incompatibile: {problems}", report)
    tables = {name: table for name, table in metadata.tables.items() if name in EXPECTED}
    return GameSchema(GameModels(tables, unsupported), report)


def schema_unavailable_error(exc: Exception) -> Exception:
    """L'`HTTPException` 503 `world.unavailable` per un `SchemaUnavailable`."""
    return api_error(503, "world.unavailable", detail=str(exc)[:300])


Loader = Callable[[str], GameSchema]
