<!-- shortcut: path relativo, PyPI non lo rende; dopo la creazione del repo GitHub usare l'URL raw assoluto
     (https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg). Vedi RELEASING.md. -->
<p align="center"><img src="../../docs/assets/logo.svg" alt="pachimudeditor" width="160"></p>

# pachimudeditor-adapter-dikumod

Adapter `kind: dikumod` di **pachimudeditor** (editor web di zone, stanze, mob e oggetti per MUD): legge (e, con `read_only: false`, scrive) i file dati di Diku Modificato (`dikumod` e `dikumod2`), con la libreria standalone `dikumod_lib` e le regole di conversione da/verso gli altri mondi.

Installazione (richiede Python 3.14+):

```bash
pip install 'pachimudeditor[dikumod]'     # oppure: pip install pachimudeditor pachimudeditor-adapter-dikumod
pachimudeditor adapters list           # verifica che l'adapter sia visto
```

Esempio di mondo in `pachimudeditor.yaml`:

```yaml
webeditor_worlds:
  - { id: dikumod, kind: dikumod, name: Diku Modificato, path: /percorso/dikumod2/lib, params: { variant: dikumod2 } }
```

Parametri, capability, limiti e formati sono nella documentazione di pachimudeditor, sezione *Adapter > dikumod*.
L'adapter richiede una versione compatibile del core (`pachimudeditor>=0.1.0,<0.2`).
