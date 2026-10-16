"""Plugin dell'adapter generico `kind: mapping` (entry point `pachimudeditor.adapters`). Solo riferimenti a stringa."""

from pachimudeditor.sdk import AdapterPlugin

plugin = AdapterPlugin(
    kind="mapping",
    sdk_version="1.0",
    description="qualunque MUD su file descritto da un YAML di mappatura (param `mapping`, esempi rom.yaml / diku_classic.yaml)",
    factory="pachimudeditor_adapter_mapping.adapter:MappingAdapter",
    modules=("pachimudeditor_adapter_mapping.module:module",),
    example="""\
# MUD descritto da un YAML di mappatura (vedi docs/adapters/mapping-guide.md):
# - { id: tba, kind: mapping, name: tbaMUD, mapping: /percorso/tba.mapping.yaml, path: /percorso/tba/lib }
""",
)
