# Configurazione dei mondi


Priorita': variabili d'ambiente > `.env` della cartella > `pachimudeditor.yaml` > default.

- `pachimudeditor.yaml` e' il file YAML di pachifast (sezioni `server`, `app`, `auth`, `events`; il CLI imposta
  `PACHIFAST_CONFIG_FILE`). Chiavi del webeditor: `webeditor_worlds`, `webeditor_default_world`,
  `webeditor_convert_journal_dir`, `config_path` (dentro il mondo pachimud). Segreti (`PACHIFAST_SECRET_KEY`, URL con password) solo in `.env`.
- Limite di richieste su conversioni e import zone: `rate_limit.default` (env `PACHIFAST_RATE_LIMIT_DEFAULT`, default dell'editor 60, `0` = spento) e
  `rate_limit.window_seconds` (default 60); alias deprecati `WEBEDITOR_HEAVY_RATE_LIMIT`/`_WINDOW`. Vedi [Sicurezza](security.md).
- Sessione: `auth.refresh_mode` (env `PACHIFAST_REFRESH_MODE`) vale `cookie` per default nell'editor (pachifast ha `body`): il
  refresh token (richiede `pachifast>=0.18.0`: tollera il refresh ripetuto entro `refresh_reuse_grace_seconds`) sta in un cookie `HttpOnly`, `SameSite=Lax`, `Path=/api/auth`, e la SPA (`refreshMode: 'cookie'`, `QCLI_AUTH_REFRESH_MODE`
  in build) non scrive token nel browser. `Secure` e' automatico su https (dietro un reverse proxy avvia uvicorn con
  `--proxy-headers`, o forza `refresh_cookie_secure`); su `http://localhost` funziona. Serve la stessa origine per SPA e `/api`
  (il backend serve la SPA, il proxy di sviluppo di Quasar e il reverse proxy di produzione lo garantiscono e devono inoltrare
  `X-Pachi-Auth` e `Host`); con origini diverse elenca la SPA in `refresh_allowed_origins` e in `cors_origins`. Con `pnpm dev` (SPA su :9010) non serve nulla: il proxy di sviluppo di `@ilpachi/pachifastquasar` (>=0.1.6) riscrive anche l'`Origin`. Dettagli in [Sicurezza](security.md).
- Mondi: `WEBEDITOR_WORLDS` (JSON) e `WEBEDITOR_DEFAULT_WORLD`, con alias `PACHIMUDEDITOR_WORLDS` /
  `PACHIMUDEDITOR_DEFAULT_WORLD` (i `WEBEDITOR_*` hanno la precedenza).
- `read_only` per mondo: `kind: dikumod` e' in sola lettura se non scritto (la scrittura va abilitata con `read_only: false`);
  `basedmud`, `mapping` e gli altri scrivono per default (`read_only: true` per proteggerli). Vedi [Diku Modificato](../adapters/dikumod.md).
- Mondo pachimud (`kind: pachimud`), parametri in `params`:

  ```yaml
  webeditor_worlds:
    - id: pachimud
      kind: pachimud
      name: Pachimud
      params:
        database_url: sqlite+aiosqlite:////percorso/pachimud.db   # URL SQLAlchemy async
        definitions_path: /percorso/definitions                    # races/, classes/ (e zones/)
        # config_path: /percorso/pachimud.yaml   # facoltativo: ne legge database_url/definition_path
  ```

  I path SQLite/`definitions_path` relativi si risolvono rispetto alla cartella di lavoro; `config_path` (il `pachimud.yaml`
  del game server) fornisce i valori mancanti e i suoi path relativi si risolvono rispetto alla sua cartella; i parametri
  espliciti vincono. Ripiego: senza `database_url` e `config_path`, la variabile `PACHIMUD_CONFIG_PATH`. All'avvio (e con
  `pachimudeditor worlds check`) si verifica la revisione alembic del database: revisione ignota o colonne assenti sono
  avvisi, e le funzioni collegate (es. `race_id` dei mob) si disattivano; dettagli in la [guida agli adapter](../adapters/sdk.md).
- Il DB dell'editor (utenti, ecc.) e' il DB di autenticazione di pachifast, SEPARATO dai database dei MUD: le
  connessioni ai MUD le gestiscono solo gli adapter.
- DB auth e migration: `init` genera `migrations/auth/` e `project_modules.py` NELLA cartella di lavoro (pachifast
  li cerca li') e applica `upgrade head`; funziona da un wheel pulito perche' le tabelle sono quelle del core pachifast.
  Dopo un aggiornamento di pachifast con modifiche allo schema: `cd <workdir> && pachifast migrations revision
  "..." --target-name auth --autogenerate && pachifast migrations upgrade --target-name auth`.

La SPA usa path assoluti (`/assets/...`): va servita dalla radice del dominio (reverse proxy senza prefisso).
Unit systemd di esempio: `pachimudeditor.service`.


Per i parametri specifici di ogni tipo di mondo vedi la pagina dell'adapter: [pachimud](../adapters/pachimud.md), [basedmud](../adapters/basedmud.md), [dikumod](../adapters/dikumod.md), [mapping](../adapters/mapping.md).
