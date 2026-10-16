<!-- shortcut: path relativo, PyPI non lo rende; dopo la creazione del repo GitHub usare l'URL raw assoluto
     (https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg). Vedi RELEASING.md. -->
<p align="center"><img src="../../docs/assets/logo.svg" alt="pachimudeditor" width="160"></p>

# pachimudeditor-adapter-mapping

Adapter `kind: mapping` di **pachimudeditor** (editor web di zone, stanze, mob e oggetti per MUD): legge e scrive i file di dati di un qualunque MUD descritto da un YAML di mappatura (layout dei file, grammatica dei record, mapping sui campi neutri). Include esempi pronti (ROM, Diku classico, MiniMUD) e lo schema JSON per l'autocompletamento.

Installazione (richiede Python 3.14+):

```bash
pip install 'pachimudeditor[mapping]'     # oppure: pip install pachimudeditor pachimudeditor-adapter-mapping
pachimudeditor adapters list           # verifica che l'adapter sia visto
```

Esempio di mondo in `pachimudeditor.yaml`:

```yaml
webeditor_worlds:
  - { id: tba, kind: mapping, name: tbaMUD, mapping: /percorso/tba.mapping.yaml, path: /percorso/tba/lib }
```

Parametri, capability, limiti e formati sono nella documentazione di pachimudeditor, sezione *Adapter > mapping*.
L'adapter richiede una versione compatibile del core (`pachimudeditor>=0.1.0,<0.2`).
