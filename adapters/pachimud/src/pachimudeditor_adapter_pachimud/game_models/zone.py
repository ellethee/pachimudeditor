# Copia di pachimud/zone/models.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

"""The `Zone` model: a named, versioned range of content vnums."""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pachimudeditor_adapter_pachimud.game_models.base import Base
from pachimudeditor_adapter_pachimud.game_models.sa_helpers import int_enum_column

from pachimudeditor_adapter_pachimud.game_models.enums import ZoneCommandType, ZoneResetMode

if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.game_models.mob import MobPrototype
    from pachimudeditor_adapter_pachimud.game_models.object import ObjectPrototype

    from pachimudeditor_adapter_pachimud.game_models.room import Room


class ZoneResetCommand(Base):
    """One ordered step of a zone's reset script (ROM's M/O/G/E/P/D/R).

    `arg1`..`arg4` are typed slots whose meaning depends on
    `command_type`, matching ROM's own reset value fields
    (`reset_value_type`, `db.c::load_resets`) — e.g. for `LOAD_MOB`:
    mob vnum, max existing world-wide, room vnum, max existing in
    that room (`None` = no per-room cap, only the global one).
    `order_index` fixes execution order within the zone, since reset
    commands are order-dependent (e.g. `GIVE_OBJECT` must follow the
    `LOAD_MOB` it applies to).
    """

    __tablename__ = "zone_reset_command"

    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zone.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(nullable=False)
    command_type: Mapped[ZoneCommandType] = int_enum_column(ZoneCommandType, nullable=False)
    if_flag: Mapped[bool] = mapped_column(nullable=False, default=False)
    arg1: Mapped[int | None] = mapped_column(default=None, nullable=True)
    arg2: Mapped[int | None] = mapped_column(default=None, nullable=True)
    arg3: Mapped[int | None] = mapped_column(default=None, nullable=True)
    arg4: Mapped[int | None] = mapped_column(default=None, nullable=True)
    arg_str: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """The one reset value ROM itself encodes as a free string rather than a number: `EQUIP_OBJECT`'s
    wear slot and `SET_DOOR_STATE`'s door state. Kept as a plain string rather than a new int
    encoding, matching this project's own choice for `ObjectInstance.equipped_slot`/
    `ObjectPrototype.wear_flags` — free strings, not a `WEAR_*`-style enum."""

    zone: Mapped["Zone"] = relationship(back_populates="reset_commands")


class Zone(Base):
    """A builder-owned area of the world, identified by a unique vnum.

    `bottom_vnum`/`top_vnum` describe the conventional vnum range the
    zone's own rooms/mobs/objects should fall in, but this is not
    enforced as a database constraint — it's advisory metadata a
    future world-editing tool can use, the same way ROM treats it
    (`area_data.min_vnum`/`max_vnum`).
    """

    __tablename__ = "zone"

    id: Mapped[int] = mapped_column(primary_key=True)
    vnum: Mapped[int] = mapped_column(unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    builder: Mapped[str] = mapped_column(nullable=False)
    bottom_vnum: Mapped[int] = mapped_column(nullable=False)
    top_vnum: Mapped[int] = mapped_column(nullable=False)
    min_level: Mapped[int] = mapped_column(default=1, nullable=False)
    max_level: Mapped[int] = mapped_column(default=1, nullable=False)
    """Recommended player level range for the zone (ROM's `area_data.low_range`/`high_range`)
    — advisory only, not enforced, same spirit as `bottom_vnum`/`top_vnum`."""
    lifespan_minutes: Mapped[int] = mapped_column(nullable=False)
    reset_mode: Mapped[ZoneResetMode] = int_enum_column(ZoneResetMode, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, server_default=sa.true(), nullable=False)
    """`False` switches the zone off without deleting it: the game never resets it, hides the exits that
    lead into it and lists it nowhere; the web editor hides it (and its content) unless asked to show it."""

    rooms: Mapped[list["Room"]] = relationship(back_populates="zone")
    mob_prototypes: Mapped[list["MobPrototype"]] = relationship(back_populates="zone")
    object_prototypes: Mapped[list["ObjectPrototype"]] = relationship(back_populates="zone")
    reset_commands: Mapped[list["ZoneResetCommand"]] = relationship(back_populates="zone", order_by="ZoneResetCommand.order_index")
