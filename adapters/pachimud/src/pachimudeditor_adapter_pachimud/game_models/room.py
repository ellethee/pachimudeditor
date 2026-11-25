# Copia di pachimud/zone/room/models.py (MUD pachimud): oggetti a terra delle stanze SAVE_ROOM.
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# L'editor non legge questa tabella (`schema.UNUSED_TABLES`): il modello serve a tenere allineato lo schema dei test.

from sqlalchemy.orm import Mapped, mapped_column

from pachimudeditor_adapter_pachimud.game_models.base import Base
from pachimudeditor_adapter_pachimud.game_models.sa_helpers import json_dict_list_column


class RoomObjects(Base):
    """Gli oggetti a terra di una stanza `SAVE_ROOM` (`world/<vnum>` di LeU), nel formato di `Object.to_json`."""

    __tablename__ = "room_objects"

    room_vnum: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    objects: Mapped[list[dict]] = json_dict_list_column(default=list, nullable=False)
