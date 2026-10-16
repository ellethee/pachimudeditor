"""Plugin dell'adapter Diku Modificato (entry point `pachimudeditor.adapters`). Solo riferimenti a stringa: nulla di pesante."""

from pachimudeditor.sdk import AdapterPlugin

plugin = AdapterPlugin(
    kind="dikumod",
    sdk_version="1.0",
    description="Diku Modificato (dikumod / dikumod2): file dati Diku dikumoddata.*, scripts.dat, gilde (libreria dikumod_lib inclusa)",
    factory="pachimudeditor_adapter_dikumod.adapter:DikumodAdapter",
    modules=("pachimudeditor_adapter_dikumod.module:module",),
    flavor="pachimudeditor_adapter_dikumod.convert:DikumodFlavor",
    example="""\
# Diku Modificato (file dati Diku; in sola lettura se read_only non e' scritto):
# - { id: dikumod, kind: dikumod, name: Diku Modificato, path: /percorso/dikumod2/lib, params: { variant: dikumod2, data_prefix: miomondo } }
# `params.data_prefix` (facoltativo, default dikumoddata): prefisso dei file dati (miomondo.wld, miomondo.mob, ...)
""",
)
