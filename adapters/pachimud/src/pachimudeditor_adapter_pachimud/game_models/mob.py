# Copia di pachimud/mob/models.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

"""The `MobPrototype` model: the template a live mob instance is spawned from."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pachimudeditor_adapter_pachimud.game_models.enums import Sex
from pachimudeditor_adapter_pachimud.game_models.base import Base
from pachimudeditor_adapter_pachimud.game_models.sa_helpers import int_enum_column, json_str_list_column

if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.game_models.zone import Zone


class MobPrototype(Base):
    """A mobile (NPC/monster) prototype.

    Hit points and bare-hand damage are stored as normalized dice
    (count/die size/bonus) rather than a "2d8+10"-style string, so a
    future balancing tool can query/aggregate them directly instead
    of parsing dice notation.
    """

    __tablename__ = "mob_prototype"

    id: Mapped[int] = mapped_column(primary_key=True)
    vnum: Mapped[int] = mapped_column(unique=True, index=True, nullable=False)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zone.id"), nullable=False, index=True)
    keywords: Mapped[str] = mapped_column(nullable=False)
    short_description: Mapped[str] = mapped_column(nullable=False)
    long_description: Mapped[str] = mapped_column(nullable=False)
    detailed_description: Mapped[str] = mapped_column(nullable=False)
    level: Mapped[int] = mapped_column(nullable=False)
    thac0: Mapped[int] = mapped_column(nullable=False)
    armor_class: Mapped[int] = mapped_column(nullable=False)
    hp_dice_count: Mapped[int] = mapped_column(nullable=False)
    hp_die_size: Mapped[int] = mapped_column(nullable=False)
    hp_bonus: Mapped[int] = mapped_column(nullable=False)
    damage_dice_count: Mapped[int] = mapped_column(nullable=False)
    damage_die_size: Mapped[int] = mapped_column(nullable=False)
    damage_bonus: Mapped[int] = mapped_column(nullable=False)
    gold: Mapped[int] = mapped_column(nullable=False)
    experience: Mapped[int] = mapped_column(nullable=False)
    sex: Mapped[Sex] = int_enum_column(Sex, nullable=False)
    flags: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    race_id: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """Id di una `BaseRace` (ROM's `mob_index_data.race`, un indice nella stessa `race_table`
    usata anche per i PC — vedi `BaseRace.mob_only`) — plain string come `class_id`/`race_id`
    altrove, non FK: le razze sono contenuto YAML statico, non righe di DB. `None`: non
    impostata (mob senza corpo fisico rilevante, es. elementali/costrutti astratti)."""
    class_id: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """Id di una `BaseClass` — non e' un concetto ROM (i mob non hanno classe, le loro stat
    di combattimento vengono dal file mob stesso), aggiunto come estensione voluta di questo
    progetto. `None`: nessuna classe (la stragrande maggioranza dei mob)."""
    debuff_skill_id: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """Id of a `content/skills/*.yaml` `DEBUFF`-type `Skill` this mob can
    cast on the player instead of a normal melee attack (see
    `etemud.server.combat._mob_attacks_player`/
    `_mob_casts_debuff_on_player`) — `None` (the default) means the mob
    only ever melees, unchanged behavior. Not a tbaMUD port: real
    tbaMUD mob-casting lives in per-mob `MOB_SPEC` C procedures with no
    generic, data-driven equivalent — this is a reasoned, invented
    mechanic to give item-granted saving-throw bonuses something to
    actually resist."""
    alignment: Mapped[int] = mapped_column(default=0, nullable=False)
    """-1000 (evil) to 1000 (good), tbaMUD's `GET_ALIGNMENT` — see
    `etemud.server.alignment` for the good/evil/neutral thresholds and
    `combat._handle_mob_damage`'s `change_alignment()` port, which
    nudges a killer's own alignment away from this value. Copied
    straight from the source `.mob` file by `scripts/
    import_ravnfjord.py`; defaults to `0` (neutral) for any mob a
    builder hasn't set one for."""
    shop_id: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """Id of a `content/shops/*.yaml` `Shop` this mob runs — `SPECIAL(shop_keeper)`
    (`src/shop.c`), assigned generically via a mob field rather than tbaMUD's separate
    `shop_index`-to-keeper-vnum table, since `MobPrototype` already has this kind of
    static-content-id slot pattern (`debuff_skill_id`). `None` (the default): an ordinary mob,
    not a shopkeeper — see `etemud.server.commands.cmd_buy`/`cmd_sell`/`cmd_list`/`cmd_value`."""
    quest_ids: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    """Ids of `content/quests/*.yaml` `Quest` entries this mob offers as a questmaster
    (`QST_MASTER`, `SPECIAL(questmaster)`, `src/quest.c`) — empty (the default) means an
    ordinary mob, offers nothing. See `etemud.server.commands.cmd_quest`."""
    is_banker: Mapped[bool] = mapped_column(default=False, nullable=False)
    """`SPECIAL(bank)` (`src/spec_procs.c`) assignment — a plain flag, not a content id like
    `shop_id`/`quest_ids`: tbaMUD's bank has no per-mob configuration (no interest rate, no
    balance cap), so there's nothing for a `content/banks/*.yaml` file to hold. `False` (the
    default): an ordinary mob, not a banker — see `etemud.server.commands.cmd_balance`/
    `cmd_deposit`/`cmd_withdraw`."""

    teaches_class_ids: Mapped[list[str] | None] = json_str_list_column(default=None, nullable=True)
    """Which classes a `guildmaster`-flagged mob trains (`etemud.server.guildmasters`): ids of
    `content/classes/*.yaml`. `None` (the default) teaches every class, as any guildmaster always did;
    the editor normalises an empty list to `None`. Only read when the `guildmaster` flag is set."""
    teaches_skill_ids: Mapped[list[str] | None] = json_str_list_column(default=None, nullable=True)
    """Which content skills (`Skill.id`, spells and percentage abilities alike) a `guildmaster`-flagged
    mob trains. `None` (the default) teaches every skill the character may otherwise learn/practice;
    a list restricts the mob to exactly those. Same emptiness/flag rules as `teaches_class_ids`."""

    zone: Mapped["Zone"] = relationship(back_populates="mob_prototypes")


class MobInstance(Base):
    """A mob actually present in a room, spawned from a `MobPrototype` by a zone reset.

    Kept deliberately minimal: no relationships, no combat state
    beyond current HP. `room_id` is non-nullable — unlike
    `PlayerCharacter.current_room_id`, a mob never exists in "the
    void": it is only ever created already placed in a room (by
    `etemud.server.zone_reset`), so there is no equivalent bootstrap
    gap to model.
    """

    __tablename__ = "mob_instance"

    id: Mapped[int] = mapped_column(primary_key=True)
    prototype_id: Mapped[int] = mapped_column(ForeignKey("mob_prototype.id"), nullable=False, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False, index=True)
    hit_points_current: Mapped[int] = mapped_column(nullable=False)
    hit_points_max: Mapped[int] = mapped_column(nullable=False)
    """The dice roll (`hp_dice_count`/`hp_die_size`/`hp_bonus` on the
    owning `MobPrototype`) this instance spawned with — stamped once at
    spawn (`etemud.server.zone_reset._spawn_mob`) and never changed
    afterward. Needed so `etemud.server.commands.cmd_flee`'s XP-loss
    penalty (`(max - current) * mob level`, ported from tbaMUD's
    `do_flee()`) has a `max` to subtract from; before this field, only
    the rolled starting HP was ever persisted, with nothing recording
    what it started at once damage brought `hit_points_current` down."""
    gold: Mapped[int | None] = mapped_column(default=None, nullable=True)
    """A shopkeeper's remaining cash reserve — `SHOP_BANK` (`src/shop.c`), only meaningful
    when the mob's `MobPrototype.shop_id` resolves to a `Shop` with `unlimited_cash=False`.
    `None` for every other mob, and for a limited-cash shopkeeper until the first time
    `cmd_sell` lazily seeds it from `Shop.starting_cash`. Deliberately separate from
    `MobPrototype.gold` (a fixed on-death kill reward, unrelated to a shop's till)."""
    master_character_id: Mapped[int | None] = mapped_column(ForeignKey("player_character.id"), default=None, nullable=True, index=True)
    """The character this mob is charmed by (`ch->master` with `AFF_CHARM`, tbaMUD's `spell_charm`)
    — `None` (the default) for every free mob. A charmed mob follows its master around
    (`etemud.server.charm.follow_master`), obeys `order` (`etemud.server.mob_actions`) and never
    acts on its own against him (`etemud.server.mob_ai`). Set by `etemud.server.charm.charm_mob`,
    cleared by `clear_charm` when `charmed_until` passes, the master dies, or he leaves the game."""
    charmed_until: Mapped[datetime | None] = mapped_column(default=None, nullable=True)
    """When the charm ends (the `SPELL_CHARM` affect's duration, `spells.c:285-291`), naive UTC as
    SQLite stores it — swept by `etemud.server.charm.expire_charms` from the mob ticker. `None`
    whenever `master_character_id` is."""
