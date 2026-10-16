---
template: home.html
hide:
  - navigation
  - toc
---

# pachimudeditor

Editor web di zone, stanze, mob e oggetti per **pachimud** e, tramite adapter, per altri MUD (basedmud/ROM, Diku Modificato,
qualunque MUD su file descritto da un YAML di mappatura). Un unico pacchetto Python installabile: backend
[pachifast](https://pypi.org/project/pachifast/) (FastAPI) e frontend Quasar gia' incluso, con il comando `pachimudeditor`.

```bash
uv tool install 'pachimudeditor[all]'
pachimudeditor init --workdir ~/pachimudeditor
pachimudeditor serve --workdir ~/pachimudeditor --open
```

## Dove andare

- **[Guida](guide/installation.md)**: installazione, comandi, configurazione dei mondi.
- **[Backend](backend/index.md)**: contratto delle API per il frontend e per integrazioni.
- **[Frontend](frontend/index.md)**: le pagine dell'editor e le capability dei mondi.
- **[Adapter](adapters/index.md)**: come l'editor parla con i MUD, un adapter per tipo di mondo e come scriverne uno.
- **[Formati](formats/dikumod.md)** e **[Conversione](conversion.md)** tra mondi.
- **[Rilasci](releasing.md)** e **[Changelog](changelog.md)**.

## Pacchetti

Il progetto e' composto da cinque pacchetti con versioni indipendenti: `pachimudeditor` (core) e gli adapter
`pachimudeditor-adapter-pachimud`, `-basedmud`, `-dikumod`, `-mapping`. Ogni adapter dichiara l'intervallo di versioni del core
compatibile; la compatibilita' dell'API per gli adapter e' espressa da `SDK_VERSION` del core.
