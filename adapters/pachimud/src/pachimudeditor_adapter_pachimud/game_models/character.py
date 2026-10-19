# Copia di pachimud/character/models.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

"""The `PlayerCharacter` model: a player-controlled character owned by an `Account`."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pachimudeditor_adapter_pachimud.game_models.base import Base
from pachimudeditor_adapter_pachimud.game_models.sa_helpers import int_enum_column, json_int_dict_column, json_str_list_column

from pachimudeditor_adapter_pachimud.game_models.enums import Position, Sex

if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.game_models.account import Account
    from pachimudeditor_adapter_pachimud.game_models.room import Room


class PlayerCharacter(Base):
    """A character a player logs in as. No inventory/equipment yet —

    those belong to a future game-server layer once there's a live game
    loop to enforce their rules; this model only covers what's needed
    to plausibly authenticate as a character, know where it last was,
    and carry the class/race/stats chosen at creation.

    `class_id`/`race_id` are plain strings, not foreign keys: classes
    and races are static YAML content loaded by `etemud.content`, not
    database rows (see `etemud.content.loader`), so there is nothing
    in this database for a foreign key to point at. Validity is
    checked at character-creation time against the loaded content
    registry, not by the database.

    `current_room_id` is nullable because no starting-room logic exists
    at this persistence-only layer; a future game server decides where
    a freshly created character (or one whose room no longer exists)
    ends up.
    """

    __tablename__ = "player_character"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    level: Mapped[int] = mapped_column(default=1, nullable=False)
    experience: Mapped[int] = mapped_column(default=0, nullable=False)
    hit_points_current: Mapped[int] = mapped_column(nullable=False)
    hit_points_max: Mapped[int] = mapped_column(nullable=False)
    gold: Mapped[int] = mapped_column(default=0, nullable=False)
    current_room_id: Mapped[int | None] = mapped_column(ForeignKey("room.id"), default=None, nullable=True, index=True)
    sex: Mapped[Sex] = int_enum_column(Sex, nullable=False)
    class_id: Mapped[str] = mapped_column(nullable=False)
    race_id: Mapped[str] = mapped_column(nullable=False)
    strength: Mapped[int] = mapped_column(nullable=False)
    strength_percentile: Mapped[int] = mapped_column(default=0, nullable=False)
    """Percentile 0-100 di forza eccezionale ("18/xx"), significativo solo
    quando `strength == 18`. In tbaMUD (`str_add`) solo il Guerriero lo
    tira alla creazione, e solo se la Forza risultante dal tiro è
    esattamente 18 (`roll_real_abils()`, `src/class.c:1417-1426`) — ogni
    altra classe/situazione resta a 0, che `ability_tables.str_app`
    interpreta come "non eccezionale", usando la riga normale della
    tabella."""
    dexterity: Mapped[int] = mapped_column(nullable=False)
    constitution: Mapped[int] = mapped_column(nullable=False)
    intelligence: Mapped[int] = mapped_column(nullable=False)
    wisdom: Mapped[int] = mapped_column(nullable=False)
    charisma: Mapped[int] = mapped_column(nullable=False)
    mana_current: Mapped[int] = mapped_column(nullable=False)
    mana_max: Mapped[int] = mapped_column(nullable=False)
    known_skill_ids: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    """Ids of `etemud.content.models.Skill` entries this character has
    learned (via `learn`/`impara`), resolved against `ServerState.
    skill_registry` — like `class_id`/`race_id`, not a foreign key:
    skills are static YAML content, not database rows."""
    practices: Mapped[int] = mapped_column(default=0, nullable=False)
    """Punti pratica accumulati, spendibili con `pratica`/`practice` per
    alzare la percentuale di riuscita di un'abilità conosciuta
    (`skill_percentages`). Guadagnati a ogni livello via
    `class_tables.practices_per_level()`."""
    skill_percentages: Mapped[dict[str, int]] = json_int_dict_column(default=dict, nullable=False)
    """Percentuale di riuscita (0-100) per id di `Skill` conosciuta, più
    la chiave sintetica `"backstab"` per il Ladro (non è un `Skill` di
    contenuto, è un comando dedicato — vedi `etemud.server.commands.
    cmd_backstab`). Una skill assente da questo dict ha percentuale 0
    (appena imparata, mai praticata)."""
    alignment: Mapped[int] = mapped_column(default=0, nullable=False)
    """-1000 (evil) to 1000 (good), tbaMUD's `GET_ALIGNMENT`, default
    `0` (neutral) at creation — tbaMUD itself starts every new
    character at alignment 0. Shifts on every kill (`etemud.server.
    combat._handle_mob_damage`, ports `change_alignment()`) and gates
    `ObjectPrototype.extra_flags`' `anti_good`/`anti_evil`/
    `anti_neutral` in `cmd_wear` (`etemud.server.alignment.
    is_forbidden_by_alignment`, ports `invalid_align()`). See
    `etemud.server.alignment` for the good/evil/neutral thresholds."""
    preferences: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    """Names of the `PRF_*` toggles currently switched on (`etemud.server.preferences.
    PREFERENCES`) — tbaMUD's `PRF_FLAGS(ch)` bitvector, one string per set bit, same shape as
    `known_skill_ids`. Channel opt-outs are stored as their `no*` name (`notell`, `noshout`, ...),
    like tbaMUD's own `PRF_NOTELL`/`PRF_NOSHOUT`/..."""
    position: Mapped[Position] = mapped_column(default=Position.STANDING, nullable=False)
    """`GET_POS(ch)`, minus the states etemud derives instead of storing: one of `Position.STANDING`,
    `Position.SITTING`, `Position.RESTING`, `Position.SLEEPING` (`etemud.server.positions`). `FIGHTING` is never stored —
    it's "standing while in `ServerState.fights`". Reset to `Position.STANDING` at login."""
    hunger: Mapped[int] = mapped_column(default=24, nullable=False)
    thirst: Mapped[int] = mapped_column(default=24, nullable=False)
    drunk: Mapped[int] = mapped_column(default=0, nullable=False)
    """`GET_COND(ch, HUNGER/THIRST/DRUNK)` (`src/structs.h:493-495`, `etemud.server.conditions`):
    `hunger`/`thirst` start full at 24 and fall one point per regen tick, `drunk` starts sober at 0.
    `-1` means the condition never changes."""
    poison_ticks: Mapped[int] = mapped_column(default=0, nullable=False)
    """Remaining ticks of poison (`AFF_POISON` duration): 2 damage and quartered regen per tick."""
    wimpy_level: Mapped[int] = mapped_column(default=0, nullable=False)
    """HP threshold (0-500, `wimpy`/`impaurisciti`) below which the
    character auto-flees a fight instead of taking the next hit —
    `GET_WIMP_LEV` (`src/prefedit.c`, `MAX(0, MIN(number, 500))`); tbaMUD
    exposes it through a preferences menu rather than a direct command,
    simplified here to a single `cmd_wimpy`. `0` (the default) disables
    it, matching tbaMUD's own "0 = off" convention — see
    `etemud.server.combat._player_attempts_wimpy_flee`."""
    is_player_killer: Mapped[bool] = mapped_column(default=False, nullable=False)
    """`PLR_KILLER` (`src/fight.c`'s `check_killer()`): set the first
    time this character initiates a fight against another player
    (`cmd_attack`, targeting a `PlayerCharacter` rather than a
    `MobInstance`) — a minimal, hardcoded stand-in for tbaMUD's
    `CONFIG_PK_SETTING == CONFIG_PK_LIMITED` mode (etemud has no
    server-config system to make PK "off"/"limited"/"unlimited"
    switchable). Attacking an already-flagged killer never flags the
    attacker in turn, same as the original — killing a known killer is
    "fair game". `PLR_THIEF` (tbaMUD's other `check_killer`-exempt
    flag, set by stealing from a player) is not ported: etemud's
    `cmd_steal` only ever targets mobs, so nothing could set it."""
    title: Mapped[str] = mapped_column(default="", nullable=False)
    """`GET_TITLE` (`do_title`, `src/act.other.c`): a free-text suffix shown after the
    character's name in `who`/`score`, e.g. "Aldric the Brave". Empty string (not `None`,
    matching tbaMUD's own `""` default) means no title set. `PLR_NOTITLE`/the `(`/`)`-forbidding
    validation live in `etemud.server.commands.cmd_title`, not here."""
    active_quest_ids: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    """Ids of `content/quests/*.yaml` `Quest` entries currently accepted but not finished —
    `quest.c`'s per-character quest state, kept here rather than a join table for the same
    reason as `known_skill_ids`: a handful of ids, read/written whole, never queried in SQL."""
    completed_quest_ids: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    """Ids of `Quest` entries already finished — `quest history` (`quest_hist()`), and checked
    by `cmd_quest`'s "list" so an already-done quest isn't offered again."""
    quest_progress: Mapped[dict[str, int]] = json_int_dict_column(default=dict, nullable=False)
    """`active_quest_ids` entry -> kills toward that quest's `Quest.quantity` so far. Cleared
    of an id the moment that quest is completed or abandoned."""
    quest_points: Mapped[int] = mapped_column(default=0, nullable=False)
    """`GET_QUESTPOINTS` — the running total of every completed quest's `Quest.
    quest_points_reward`, shown by `score`."""
    bank_gold: Mapped[int] = mapped_column(default=0, nullable=False)
    """`GET_BANK_GOLD` (`SPECIAL(bank)`, `src/spec_procs.c`) — gold deposited at a banker mob
    (`MobPrototype.is_banker`), separate from carried `gold`: safe from `spawn_player_corpse`'s
    on-death gold wipe, exactly like a real tbaMUD bank balance. See `etemud.server.commands.
    cmd_balance`/`cmd_deposit`/`cmd_withdraw`."""
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC))
    last_played_at: Mapped[datetime | None] = mapped_column(default=None, nullable=True)

    account: Mapped["Account"] = relationship(back_populates="characters")
    current_room: Mapped[Optional["Room"]] = relationship(back_populates="characters_present")
