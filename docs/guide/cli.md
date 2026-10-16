# Avvio e comandi


| Comando | Cosa fa |
| --- | --- |
| `pachimudeditor init [-w DIR] [-u NOME] [--password P] [--email E] [--database-url URL] [--no-user]` | crea la cartella di lavoro, `pachimudeditor.yaml` (nessun mondo attivo, esempi commentati per ogni kind), `.env` (secret key), DB auth con migration, primo superuser; ripetibile |
| `pachimudeditor serve [-w DIR] [--host H] [--port P] [--reload/--no-reload] [--open] [--log-level L]` | API + SPA su un solo processo (default 127.0.0.1:8123) |
| `pachimudeditor users create\|ls\|update\|delete` | i comandi utenti di pachifast sulla cartella di lavoro |
| `pachimudeditor adapters list` | gli adapter (plugin) scoperti: kind, stato, pacchetto, versione; per i ufficiali non installati il comando per aggiungerli |
| `pachimudeditor worlds list\|check` | mondi configurati (id/kind/capability/sola lettura) e salute (path, numero di zone, per pachimud revisione e stato dello schema con gli avvisi), piu' i kind disponibili e quelli da installare; `check` esce 1 se fallisce |
| `pachimudeditor build-frontend [--skip-install] [--frontend-dir D]` | solo sviluppo: `pnpm install/build` + copia in `src/pachimudeditor/static` |
| `pachimudeditor info [-w DIR]` | versioni, adapter installati/mancanti, cartella di lavoro, file di config, frontend presente |
| `pachimudeditor --version`, `--workdir` (globale) | |

La cartella di lavoro e' `--workdir`, poi `$PACHIMUDEDITOR_WORKDIR`, poi la cartella corrente.

