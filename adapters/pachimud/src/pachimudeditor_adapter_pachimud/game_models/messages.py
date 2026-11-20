# Copia di pachimud/messages/models.py (MUD pachimud): bacheche e posta fra giocatori.
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; il tipo `UTCDateTime` non c'e' qui (i test usano SQLite: stessa colonna datetime).

from datetime import UTC, datetime

from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from pachimudeditor_adapter_pachimud.game_models.base import Base


class BoardMessage(Base):
    """Un messaggio su una bacheca; l'ordine (il numero che si legge con `read <n>`) e' quello dell'`id`."""

    __tablename__ = "board_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    board_id: Mapped[str] = mapped_column(index=True, nullable=False)
    author: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC))


class MailMessage(Base):
    """Una lettera in attesa all'ufficio postale; si cancella quando il destinatario la ritira."""

    __tablename__ = "mail_message"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipient: Mapped[str] = mapped_column(index=True, nullable=False)
    """Nome del destinatario in minuscolo."""
    sender: Mapped[str] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=lambda: datetime.now(UTC))
