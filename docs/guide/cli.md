# Avvio e comandi


| Comando | Cosa fa |
| --- | --- |
| `pachimudeditor init [-w DIR] [-u NOME] [--password P] [--email E] [--database-url URL] [--no-user]` | crea la cartella di lavoro, `pachimudeditor.yaml` (nessun mondo attivo, esempi commentati per ogni kind), `.env` (secret key), DB auth con migration, primo superuser, `pachimudeditor.schema.json`; ripetibile |
| `pachimudeditor schema [-o FILE\|-] [--write] [-w DIR]` | stampa su stdout il JSON Schema di `pachimudeditor.yaml` (pachifast piu' `webeditor_*`, `params` per kind); `-o FILE` lo scrive, `--write` crea `pachimudeditor.schema.json` nella cartella di lavoro |
| `pachimudeditor serve [-w DIR] [--host H] [--port P] [--reload/--no-reload] [--open] [--log-level L]` | API + SPA su un solo processo (default 127.0.0.1:8123) |
| `pachimudeditor users create\|ls\|update\|delete` | i comandi utenti di pachifast sulla cartella di lavoro |
| `pachimudeditor adapters list` | gli adapter (plugin) scoperti: kind, stato, pacchetto, versione; per i ufficiali non installati il comando per aggiungerli |
| `pachimudeditor worlds list\|check` | mondi configurati (id/kind/capability/sola lettura) e salute (path, numero di zone, per pachimud revisione e stato dello schema con gli avvisi), piu' i kind disponibili e quelli da installare; `check` esce 1 se fallisce |
| `pachimudeditor live (--world ID \| --socket PATH) [--token-env VAR] [--timeout S] [--actor NOME] [--pretty] <comando>` | client sottile del [canale live](../backend/live-control-protocol.md#client-da-riga-di-comando) verso un MUD acceso: `status`, `ping`, `info`, `who`, `player get\|set`, `zone list\|reset`, `load mob\|obj`, `echo`. JSON su stdout, exit code 0 ok / 1 errore del MUD / 2 uso / 3 irraggiungibile / 4 autenticazione / 5 esito sconosciuto. Il token solo da variabile d'ambiente (o `.env`), mai da argomenti |
| `pachimudeditor build-frontend [--skip-install] [--frontend-dir D]` | solo sviluppo: `pnpm install/build` + copia in `src/pachimudeditor/static` |
| `pachimudeditor info [-w DIR]` | versioni, adapter installati/mancanti, cartella di lavoro, file di config, frontend presente |
| `pachimudeditor --version`, `--workdir` (globale) | |

La cartella di lavoro e' `--workdir`, poi `$PACHIMUDEDITOR_WORKDIR`, poi la cartella corrente.

