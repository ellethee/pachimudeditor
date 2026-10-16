"""Adapter generico `kind: mapping`: legge e scrive i file di dati di un MUD descritto da un YAML di mappatura.

Moduli: `schema` (YAML -> `MappingSpec`), `grammar` (lettura), `writer` (scrittura), `model` (record <-> DTO), `dsl`
(espressioni sicure), `hooks` (codice richiamabile per nome), `store` (file, cache, indici) e l'adapter vero e proprio
(`adapter`, con i mixin `zones`, `rooms`, `prototypes`). Vedi `docs/adapters/index.md` e `docs/adapters/mapping-guide.md`.
"""
