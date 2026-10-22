"""Plugin dell'adapter Diku Modificato (entry point `pachimudeditor.adapters`). Solo riferimenti a stringa: nulla di pesante."""

from pachimudeditor.sdk import AdapterPlugin

plugin = AdapterPlugin(
    kind="dikumod",
    sdk_version="1.5",
    description="Diku Modificato (DikuMod1; dikumod2 non piu' considerata): file dati Diku dikumoddata.*, scripts.dat, gilde (libreria dikumod_lib inclusa)",
    factory="pachimudeditor_adapter_dikumod.adapter:DikumodAdapter",
    validate="pachimudeditor_adapter_dikumod.live_config:validate_world",
    modules=("pachimudeditor_adapter_dikumod.module:module",),
    flavor="pachimudeditor_adapter_dikumod.convert:DikumodFlavor",
    example="""\
# Diku Modificato (file dati Diku; in sola lettura se read_only non e' scritto):
# - { id: dikumod, kind: dikumod, name: Diku Modificato, path: /percorso/leu/lib, params: { data_prefix: leudata } }
# `params.data_prefix` (facoltativo, default dikumoddata): prefisso dei file dati (miomondo.wld, miomondo.mob, ...)
# `params.spec_assign` (facoltativo): percorso assoluto di spec_assign.c (default <radice>/src/spec_assign.c), letto in sola lettura
# per la procedura speciale dei mob e il filtro «insegna / gain»
# Canale live verso il MUD acceso (modulo livectl; il token sta nel .env, qui solo il NOME della variabile):
#   params: { live: { socket: /percorso/assoluto/livectl.sock, token_env: DIKUMOD_LIVE_TOKEN, timeout_ms: 3000 } }
""",
)
