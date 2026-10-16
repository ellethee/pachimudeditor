"""Plugin dell'adapter pachimud (entry point `pachimudeditor.adapters`). Solo riferimenti a stringa: nulla di pesante.

I moduli API specifici del mondo pachimud (world, players, instances, transfer, content) si registrano SOLO se e'
configurato un mondo `kind: pachimud`.
"""

from pachimudeditor.sdk import AdapterPlugin

_P = "pachimudeditor_adapter_pachimud"

plugin = AdapterPlugin(
    kind="pachimud",
    sdk_version="1.0",
    description="il gioco pachimud: database SQLAlchemy letto per riflessione (nessun import del pacchetto `pachimud`)",
    factory=f"{_P}.adapter:PachimudAdapter",
    modules=(
        f"{_P}.module:module",
        f"{_P}.apps.world.module:module",
        f"{_P}.apps.instances.module:module",
        f"{_P}.apps.players.module:module",
        f"{_P}.apps.transfer.module:module",
        f"{_P}.apps.content.module:module",
    ),
    flavor=f"{_P}.convert:PachimudFlavor",
    validate=f"{_P}.params:validate_world",
    example="""\
# Gioco pachimud: legge il database del game server con SQLAlchemy (il pacchetto `pachimud` NON serve). Parametri:
# database_url (URL SQLAlchemy async; path SQLite relativi = cartella di lavoro), definitions_path (races/, classes/),
# config_path facoltativo (il pachimud.yaml del game server: ne legge database_url/definition_path se non indicati qui).
# - id: pachimud
#   kind: pachimud
#   name: Pachimud
#   params:
#     database_url: sqlite+aiosqlite:////percorso/pachimud.db
#     definitions_path: /percorso/definitions
#     # config_path: /percorso/pachimud.yaml
""",
)
