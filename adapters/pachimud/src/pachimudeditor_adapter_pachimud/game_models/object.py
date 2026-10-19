# Copia di pachimud/object/models.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pachimudeditor_adapter_pachimud.game_models.base import Base
from pachimudeditor_adapter_pachimud.game_models.sa_helpers import int_enum_column, json_int_dict_column, json_str_list_column

from pachimudeditor_adapter_pachimud.game_models.enums import ObjectType

if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.game_models.zone import Zone


class ObjectPrototype(Base):
    """An object prototype.

    `value_0`..`value_3` are typed slots whose meaning depends on
    `object_type` (e.g. weapon dice vs. container capacity), mirroring
    tbaMUD's object value fields. Per-type value tables are left out
    of this pass as over-engineering for the current scope.

    For `ObjectType.WEAPON` (see `etemud.server.combat`): `value_0` =
    damage dice count, `value_1` = damage die size, `value_2` = damage
    bonus — same shape as `MobPrototype.damage_dice_count`/
    `.damage_die_size`/`.damage_bonus`. `value_3` is tbaMUD's raw
    attack-type offset from `TYPE_HIT` (`src/spells.h`, 0-14); `11`
    means `TYPE_PIERCE`, required to backstab (see
    `etemud.server.combat._is_wielding_piercing_weapon`) — every other
    value is some other damage type etemud's combat doesn't otherwise
    distinguish. A weapon with any of `value_0`/`value_1` unset falls back
    to a plain `1`/`4` die at combat time rather than failing.

    For `ObjectType.ARMOR`: `value_0` = armor class bonus, an integer
    subtracted from the wearer's armor class (lower AC is better, same
    convention as `MobPrototype.armor_class` and the THAC0 formula in
    `etemud.server.combat`). `value_1`..`value_3` are unused. `value_0`
    unset on an equipped armor piece counts as `0` (no bonus), not an
    error.

    For `ObjectType.CONTAINER` (see `etemud.server.commands.cmd_put`):
    `value_0` = maximum number of instances it can hold; `None` means
    unlimited. `value_1`..`value_3` are unused.

    `affects` (any `object_type`, worn OR wielded — not just armor) is
    tbaMUD's `obj_affected_type` array (`GET_OBJ_AFFECT`), a
    `BuffTarget` name to integer modifier, active only while the
    instance is equipped (`equipped_slot is not None`). Summed with
    active spell buffs by `etemud.server.affects.
    compute_active_modifiers` — see `BuffTarget`'s docstring for which
    targets are wired up and which are deliberately not yet.
    """

    __tablename__ = "object_prototype"

    id: Mapped[int] = mapped_column(primary_key=True)
    vnum: Mapped[int] = mapped_column(unique=True, index=True, nullable=False)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zone.id"), nullable=False, index=True)
    keywords: Mapped[str] = mapped_column(nullable=False)
    short_description: Mapped[str] = mapped_column(nullable=False)
    long_description: Mapped[str] = mapped_column(nullable=False)
    action_description: Mapped[str | None] = mapped_column(default=None, nullable=True)
    object_type: Mapped[ObjectType] = int_enum_column(ObjectType, nullable=False)
    weight: Mapped[int] = mapped_column(nullable=False)
    cost: Mapped[int] = mapped_column(nullable=False)
    rent: Mapped[int] = mapped_column(nullable=False)
    value_0: Mapped[int | None] = mapped_column(default=None, nullable=True)
    value_1: Mapped[int | None] = mapped_column(default=None, nullable=True)
    value_2: Mapped[int | None] = mapped_column(default=None, nullable=True)
    value_3: Mapped[int | None] = mapped_column(default=None, nullable=True)
    extra_flags: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    wear_flags: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    affects: Mapped[dict[str, int]] = json_int_dict_column(default=dict, nullable=False)

    zone: Mapped["Zone"] = relationship(back_populates="object_prototypes")


class ObjectInstance(Base):
    """An object existing in a room, in a character's or mob's possession, or inside a container.

    Application-level invariant, not enforced by the database: exactly
    one of `room_id`/`character_id`/`container_instance_id`/
    `mob_instance_id` is set at any time. `equipped_slot` is only
    meaningful when `character_id` or `mob_instance_id` is set; it is
    a free string taken from that object's prototype `wear_flags`
    (already a free `list[str]`, e.g. `"body"`/`"wield"`, tbaMUD-style
    — not a new enum, matching how `wear_flags`/`extra_flags`/`flags`
    are already modeled elsewhere).

    `mob_instance_id` exists so a zone reset's `GIVE_OBJECT`/
    `EQUIP_OBJECT` commands (see `etemud.server.zone_reset`) have
    somewhere to put what a mob spawns carrying or wearing — a mob's
    inventory isn't reachable by players directly in this pass (no
    "loot the corpse" yet), it only matters for the reset script.

    No container-inside-container nesting: `etemud.server.commands.cmd_put`
    refuses to put a `ObjectType.CONTAINER`-typed item into another
    container, so an instance reachable via `container_instance_id` is
    guaranteed to never itself be a container. That sidesteps cycle
    detection entirely rather than solving it — lifting the
    restriction later means adding a cycle check, not just relaxing
    the refusal.
    """

    __tablename__ = "object_instance"

    id: Mapped[int] = mapped_column(primary_key=True)
    prototype_id: Mapped[int] = mapped_column(ForeignKey("object_prototype.id"), nullable=False, index=True)
    room_id: Mapped[int | None] = mapped_column(ForeignKey("room.id"), default=None, nullable=True, index=True)
    character_id: Mapped[int | None] = mapped_column(ForeignKey("player_character.id"), default=None, nullable=True, index=True)
    container_instance_id: Mapped[int | None] = mapped_column(ForeignKey("object_instance.id"), default=None, nullable=True, index=True)
    mob_instance_id: Mapped[int | None] = mapped_column(ForeignKey("mob_instance.id"), default=None, nullable=True, index=True)
    equipped_slot: Mapped[str | None] = mapped_column(default=None, nullable=True)
    liquid_amount: Mapped[int | None] = mapped_column(default=None, nullable=True)
    """Current fill level of an `ObjectType.LIQUID_CONTAINER` instance — `GET_OBJ_VAL(obj, 1)`
    (`DRINK_CON_NOW`, `src/act.item.c`). Per-*instance*, not per-prototype: `ObjectPrototype.
    value_0` stays the fixed capacity every spawned copy shares (like weapon dice), but how
    full any one bottle currently is has to live here, the same way `MobInstance.hit_points_
    current` tracks a mob's live HP separately from its prototype's dice. `None` until
    `etemud.server.commands.cmd_drink`/`cmd_pour` first touches this instance, at which point
    it's lazily seeded to `value_0` (spawns full) — irrelevant for every other `ObjectType`."""
    charges: Mapped[int | None] = mapped_column(default=None, nullable=True)
    """Remaining charges of a `WAND`/`STAFF` instance — `GET_OBJ_VAL(obj, 2)` (`src/spec_procs.c`-side
    `do_use()`, `src/act.item.c`). Per-*instance* like `liquid_amount`: `ObjectPrototype.value_1` is the
    fixed maximum every copy shares, `value_2` the starting charges. `None` until first used, then
    lazily seeded from `value_2`."""
    liquid_type: Mapped[int | None] = mapped_column(default=None, nullable=True)
    """`DRINK_CON_TYPE` of this instance (`etemud.server.liquids`) once it holds something other than
    what its prototype's `value_2` says (a `pour`/`fill` changed it). `None` = the prototype's liquid."""
    liquid_poisoned: Mapped[bool | None] = mapped_column(default=None, nullable=True)
    """`DRINK_CON_POISON` of this instance; `None` = the prototype's `value_3`."""
