# Copia di pachimud/account/models.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from pachimudeditor_adapter_pachimud.game_models.base import Base


if TYPE_CHECKING:
    from pachimudeditor_adapter_pachimud.game_models.character import PlayerCharacter


class Account(Base):
    """Class representing an account in the game."""

    __tablename__ = "account"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(default=None, unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC))
    last_login_at: Mapped[datetime | None] = mapped_column(default=None, nullable=True)
    is_banned: Mapped[bool] = mapped_column(default=False, nullable=False)

    characters: Mapped[list[PlayerCharacter]] = relationship(back_populates="account")
