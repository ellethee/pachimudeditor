<!-- shortcut: path relativo, PyPI non lo rende; dopo la creazione del repo GitHub usare l'URL raw assoluto
     (https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg). Vedi RELEASING.md. -->
<p align="center"><img src="../../docs/assets/logo.svg" alt="pachimudeditor" width="160"></p>

# pachimudeditor-adapter-pachimud

Adapter `kind: pachimud` di **pachimudeditor** (editor web di zone, stanze, mob e oggetti per MUD): legge e scrive il database del gioco pachimud con SQLAlchemy (nessun import del pacchetto `pachimud`) e porta le pagine specifiche: panoramica del mondo, istanze, giocatori, trasferimento di zone (YAML) e contenuti (razze/classi).

Installazione (richiede Python 3.14+):

```bash
pip install 'pachimudeditor[pachimud]'     # oppure: pip install pachimudeditor pachimudeditor-adapter-pachimud
pachimudeditor adapters list           # verifica che l'adapter sia visto
```

Esempio di mondo in `pachimudeditor.yaml`:

```yaml
webeditor_worlds:
  - id: pachimud
    kind: pachimud
    name: Pachimud
    params:
      database_url: sqlite+aiosqlite:////percorso/pachimud.db
      definitions_path: /percorso/definitions
```

Parametri, capability, limiti e formati sono nella documentazione di pachimudeditor, sezione *Adapter > pachimud*.
L'adapter richiede una versione compatibile del core (`pachimudeditor>=0.1.0,<0.2`).
