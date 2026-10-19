<p align="center"><img src="https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg" alt="pachimudeditor" width="160"></p>

# pachimudeditor-adapter-basedmud

Adapter `kind: basedmud` di **pachimudeditor** (editor web di zone, stanze, mob e oggetti per MUD): legge e scrive i file area `.are` di basedmud / ROM 2.4 / QuickMUD, con la libreria standalone `rom_lib` (parser/writer round-trip) e le regole di conversione da/verso gli altri mondi.

Installazione (richiede Python 3.14+):

```bash
pip install 'pachimudeditor[basedmud]'     # oppure: pip install pachimudeditor pachimudeditor-adapter-basedmud
pachimudeditor adapters list           # verifica che l'adapter sia visto
```

Esempio di mondo in `pachimudeditor.yaml`:

```yaml
webeditor_worlds:
  - { id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/basedmud/area, read_only: true }
```

Parametri, capability, limiti e formati sono nella documentazione di pachimudeditor, sezione *Adapter > basedmud*.
L'adapter richiede una versione compatibile del core (`pachimudeditor>=0.1.0,<0.2`).
