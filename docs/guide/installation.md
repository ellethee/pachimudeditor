# Installazione

Requisiti: Python 3.14 o superiore. Il pacchetto `pachimudeditor` include il backend e il frontend gia' buildato; i MUD supportati arrivano dagli adapter, installabili come *extras*.


```bash
uv tool install 'pachimudeditor[all]'  # o solo gli adapter che servono: 'pachimudeditor[dikumod,basedmud]'
pachimudeditor adapters list                        # adapter installati e come aggiungere gli altri
pachimudeditor init --workdir ~/pachimudeditor     # .env, pachimudeditor.yaml, DB auth + migration, primo superuser
$EDITOR ~/pachimudeditor/pachimudeditor.yaml      # webeditor_worlds: nessun mondo e' implicito (esempi commentati per ogni kind)
pachimudeditor serve --workdir ~/pachimudeditor --open     # http://127.0.0.1:8123
```


## Adapter (kind di mondo) ed extras

| Extra | Pacchetto | `kind` | Cosa legge/scrive |
| --- | --- | --- | --- |
| `pachimud` | `pachimudeditor-adapter-pachimud` | `pachimud` | il database del gioco (SQLAlchemy) + pagine panoramica/giocatori/istanze/trasferimento/contenuti |
| `basedmud` | `pachimudeditor-adapter-basedmud` | `basedmud` | file area `.are` di basedmud / ROM 2.4 / QuickMUD |
| `dikumod` | `pachimudeditor-adapter-dikumod` | `dikumod` | file dati di Diku Modificato (`dikumod`, `dikumod2`) |
| `mapping` | `pachimudeditor-adapter-mapping` | `mapping` | qualunque MUD su file descritto da un YAML di mappatura |
| `all` | tutti i precedenti | | |

Il core da solo parte (nessun mondo, `/api/worlds` vuoto, UI con la pagina "Nessun mondo configurato"); un mondo il cui
`kind` non e' installato da' un errore che dice quale extra installare (es. `pip install 'pachimudeditor[dikumod]'`). Le pagine
specifiche di un mondo (giocatori, istanze, trasferimento, contenuti) esistono solo se l'adapter e' installato e il mondo ha
la capability. `pachimud` (il gioco) NON e' una dipendenza e non va installato: un mondo `kind: pachimud` e' solo un database
SQLite (o altro URL async) + la cartella `definitions/`, da indicare nei parametri del mondo (vedi "Configurazione").
`pachifast` si prende da PyPI. Adapter di terzi: la [guida agli adapter](../adapters/sdk.md) ("Scrivere un adapter esterno").
Senza nessun mondo configurato il server parte lo stesso (`/api/worlds` vuoto) e la UI mostra la pagina
"Nessun mondo configurato" con le istruzioni.

