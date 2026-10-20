"""Plugin dell'adapter BasedMud (entry point `pachimudeditor.adapters`). Solo riferimenti a stringa: nulla di pesante."""

from pachimudeditor.sdk import AdapterPlugin

plugin = AdapterPlugin(
    kind="basedmud",
    sdk_version="1.2",
    description="basedmud / ROM 2.4 / QuickMUD: file area .are (libreria rom_lib inclusa)",
    factory="pachimudeditor_adapter_basedmud.adapter:BasedMudAdapter",
    modules=("pachimudeditor_adapter_basedmud.module:module",),
    flavor="pachimudeditor_adapter_basedmud.convert:BasedMudFlavor",
    example="""\
# basedmud / ROM (file .are), sola lettura con read_only: true:
# - { id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/basedmud/area, read_only: true }
""",
)
