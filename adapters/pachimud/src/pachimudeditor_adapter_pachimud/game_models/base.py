# Copia di pachimud/database/base.py (MUD pachimud, ROM-like).
# COPIA: mantenere allineata con il MUD (vedi docs/contributing.md, sezione "Mantenere i modelli allineati col MUD").
# Adattamenti: import interni al pacchetto; rimossi i metodi che usano il game server (get_server).

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common declarative base for every ORM model in the project."""
