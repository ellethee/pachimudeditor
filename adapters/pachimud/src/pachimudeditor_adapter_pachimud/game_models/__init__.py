"""Modelli SQLAlchemy del database di gioco di pachimud, COPIATI dal MUD (l'editor non importa il pacchetto `pachimud`).

L'adapter, in produzione, legge il DB con la riflessione (`schema.py`) e non usa questi modelli: servono ai test, al
seed e2e e agli script per creare lo schema (`Base.metadata.create_all`) e scrivere righe come farebbe il game server.
Nel DB del gioco restano `account`, `player_character`, `board_message` e `mail_message` (i contenuti sono YAML: vedi `loaders.py`). Sono la copia di
`pachimud/{database,account,character,messages}`; per riallinearla vedi `docs/contributing.md`.

Importare questo pacchetto registra tutte le tabelle su `Base` (necessario per le relazioni con nome in stringa).
"""

from pachimudeditor_adapter_pachimud.game_models import account, character, messages  # noqa: F401
from pachimudeditor_adapter_pachimud.game_models.base import Base

__all__ = ["Base"]
