# Copia di pachimud/zone/room/models.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

"""The `Room` model: a single location in the world."""

from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pachimudeditor_adapter_pachimud.game_models.base import Base
from pachimudeditor_adapter_pachimud.game_models.sa_helpers import int_enum_column, json_str_list_column

from pachimudeditor_adapter_pachimud.game_models.enums import Direction, DoorFlag, SectorType

if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.game_models.character import PlayerCharacter
    from pachimudeditor_adapter_pachimud.game_models.zone import Zone


class Exit(Base):
    """A directional exit from a room, optionally leading nowhere.

    `target_room_id` is nullable: a `None` target mirrors tbaMUD's
    NOWHERE sentinel, an exit that's described (and shows up on
    "exits") but doesn't actually lead anywhere.

    `door_flag` is the exit's static door capability (none/closable/
    pickproof) — it never changes at runtime. `is_open` is the actual
    runtime state a `SET_DOOR_STATE` zone reset command or the
    `open`/`close` player commands flip; it's meaningless when
    `door_flag` is `NONE` (there's no door to open or close) and
    `cmd_move` only consults it when `door_flag` isn't `NONE`.

    `is_locked` is a second runtime bit, orthogonal to `door_flag`
    (which only says whether the door *can* have a lock picked —
    no picking mechanic exists) — a door can be locked only when
    `key_vnum is not None`, checked by `lock`/`unlock` and
    `SET_DOOR_STATE`'s `desired_state=2`, never by `door_flag`. A
    locked door is always closed too (`lock` refuses on an open
    door), so `cmd_move`'s existing `is_open` check already blocks
    passage through one — nothing extra to consult there.
    """

    __tablename__ = "exit"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False, index=True)
    direction: Mapped[Direction] = int_enum_column(Direction, nullable=False)
    description: Mapped[str | None] = mapped_column(default=None, nullable=True)
    keywords: Mapped[str | None] = mapped_column(default=None, nullable=True)
    door_flag: Mapped[DoorFlag] = int_enum_column(DoorFlag, default=DoorFlag.NONE, nullable=False)
    is_open: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_locked: Mapped[bool] = mapped_column(default=False, nullable=False)
    key_vnum: Mapped[int | None] = mapped_column(default=None, nullable=True)
    target_room_id: Mapped[int | None] = mapped_column(ForeignKey("room.id"), default=None, nullable=True, index=True)

    room: Mapped["Room"] = relationship(back_populates="exits", foreign_keys=[room_id])
    target_room: Mapped[Optional["Room"]] = relationship(back_populates="incoming_exits", foreign_keys=[target_room_id])


class RoomExtraDescription(Base):
    """Extra text shown when a player looks at a specific keyword in a room."""

    __tablename__ = "room_extra_description"

    id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=False, index=True)
    keywords: Mapped[str] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(nullable=False)

    room: Mapped["Room"] = relationship(back_populates="extra_descriptions")


class Room(Base):
    """A room prototype. Flags are stored as a JSON list of flag names.

    See `etemud.utils.sa_helpers.json_str_list_column` for why flags
    are JSON rather than a normalized join table.
    """

    __tablename__ = "room"

    id: Mapped[int] = mapped_column(primary_key=True)
    vnum: Mapped[int] = mapped_column(unique=True, index=True, nullable=False)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zone.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(nullable=False)
    sector_type: Mapped[SectorType] = int_enum_column(SectorType, nullable=False)
    flags: Mapped[list[str]] = json_str_list_column(default=list, nullable=False)
    heal_rate: Mapped[int] = mapped_column(default=100, nullable=False)
    mana_rate: Mapped[int] = mapped_column(default=100, nullable=False)
    """Percentage regen modifier for hp/mana while resting/sleeping here (ROM's
    `room_index_data.heal_rate`/`mana_rate`) — 100 is normal, e.g. a "sacred room"
    might use 200 or more. Applied on top of the normal regen calculation, not in
    place of it."""
    clan_id: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """Id of the clan this room is restricted to (ROM's `clan`/`clan_str`) — a plain
    string like `class_id`/`race_id`, since there is no clan system/table yet. `None`
    (the default): open to everyone."""
    owner: Mapped[str | None] = mapped_column(default=None, nullable=True)
    """Name of the character who purchased this room as housing (ROM's `owner`).
    `None` (the default): not owned, ordinary room."""

    zone: Mapped["Zone"] = relationship(back_populates="rooms")
    exits: Mapped[list["Exit"]] = relationship(back_populates="room", foreign_keys="[Exit.room_id]")
    incoming_exits: Mapped[list["Exit"]] = relationship(back_populates="target_room", foreign_keys="[Exit.target_room_id]")
    extra_descriptions: Mapped[list["RoomExtraDescription"]] = relationship(back_populates="room")
    characters_present: Mapped[list["PlayerCharacter"]] = relationship(back_populates="current_room")
    """Characters whose last-known `current_room_id` is this room.

    This is *not* "who is here right now": a disconnected character
    keeps its `current_room_id`, so this list includes offline
    characters too. Live presence is tracked by the game server's
    in-memory session registry (`etemud.server.state.ServerState`),
    not this relationship.
    """
