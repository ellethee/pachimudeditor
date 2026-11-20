<p align="center"><img src="https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg" alt="pachimudeditor" width="160"></p>

# pachimudeditor-adapter-pachimud

Adapter `kind: pachimud` di **pachimudeditor** (editor web di zone, stanze, mob e oggetti per MUD): legge e scrive i file YAML del gioco pachimud (zone, stanze, mob, oggetti, reset: `id == vnum`) e il suo database dei giocatori (account e personaggi) con SQLAlchemy (nessun import del pacchetto `pachimud`) e porta le pagine specifiche: panoramica del mondo, giocatori, trasferimento di zone (cartelle YAML) e contenuti (razze/classi). Il gioco non ricarica a caldo: le modifiche valgono al suo riavvio.

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
      definitions_path: /percorso/definitions                    # contenuti YAML (obbligatorio)
      database_url: sqlite+aiosqlite:////percorso/pachimud.db   # giocatori (facoltativo)
```

Parametri, capability, limiti e formati sono nella documentazione di pachimudeditor, sezione *Adapter > pachimud*.
L'adapter richiede una versione compatibile del core (`pachimudeditor>=0.1.0,<0.2`).
