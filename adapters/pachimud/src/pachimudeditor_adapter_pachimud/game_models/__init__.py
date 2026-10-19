"""Modelli SQLAlchemy del database di gioco di pachimud, COPIATI dal MUD (l'editor non importa il pacchetto `pachimud`).

L'adapter, in produzione, legge il DB con la riflessione (`schema.py`) e non usa questi modelli: servono ai test, al
seed e2e e agli script per creare lo schema (`Base.metadata.create_all`) e scrivere righe come farebbe il game server.
Sono la copia di `pachimud/{database,account,character,mob,object,zone}`; per riallinearla vedi `docs/contributing.md`.

Importare questo pacchetto registra tutte le tabelle su `Base` (necessario per le relazioni con nome in stringa).
"""

from pachimudeditor_adapter_pachimud.game_models import account, character, mob, object, room, zone  # noqa: F401
from pachimudeditor_adapter_pachimud.game_models.base import Base

__all__ = ["Base"]
