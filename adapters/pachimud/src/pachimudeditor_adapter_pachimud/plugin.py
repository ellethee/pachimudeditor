"""Plugin dell'adapter pachimud (entry point `pachimudeditor.adapters`). Solo riferimenti a stringa: nulla di pesante.

I moduli API specifici del mondo pachimud (world, players, transfer, content) si registrano SOLO se e'
configurato un mondo `kind: pachimud`.
"""

from pachimudeditor.sdk import AdapterPlugin

_P = "pachimudeditor_adapter_pachimud"

plugin = AdapterPlugin(
    kind="pachimud",
    sdk_version="1.0",
    description="il gioco pachimud: contenuti in file YAML (zone, stanze, mob, oggetti, reset), giocatori nel database SQLite (nessun import del pacchetto `pachimud`)",
    factory=f"{_P}.adapter:PachimudAdapter",
    modules=(
        f"{_P}.module:module",
        f"{_P}.apps.world.module:module",
        f"{_P}.apps.players.module:module",
        f"{_P}.apps.transfer.module:module",
        f"{_P}.apps.content.module:module",
    ),
    flavor=f"{_P}.convert:PachimudFlavor",
    validate=f"{_P}.params:validate_world",
    example="""\
# Gioco pachimud: contenuti = file YAML sotto definitions_path (zones/ classes/ races/); giocatori = DB SQLite del game server
# (il pacchetto `pachimud` NON serve). Parametri: definitions_path (OBBLIGATORIO, o config_path), database_url (facoltativo:
# URL SQLAlchemy async; path SQLite relativi = cartella di lavoro), config_path facoltativo (il pachimud.yaml del game server:
# ne legge database_url/definition_path se non indicati qui). Il gioco non ricarica a caldo: le modifiche valgono al riavvio
# (o con «Ricarica zona» dal canale live, se configurato).
# - id: pachimud
#   kind: pachimud
#   name: Pachimud
#   params:
#     definitions_path: /percorso/definitions
#     database_url: sqlite+aiosqlite:////percorso/pachimud.db
#     # config_path: /percorso/pachimud.yaml
#     # canale live (sezione `livectl` del pachimud.yaml; il token sta nel .env, qui solo il NOME della variabile):
#     # live: { socket: /percorso/assoluto/pachimud.sock, token_env: LIVECTL_TOKEN, timeout_ms: 3000 }
""",
)
