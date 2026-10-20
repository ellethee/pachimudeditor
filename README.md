<p align="center"><img src="https://raw.githubusercontent.com/ellethee/pachimudeditor/main/docs/assets/logo.svg" alt="pachimudeditor" width="160"></p>

# pachimudeditor

Editor web di zone, stanze, mob e oggetti di pachimud (e, tramite adapter, di altri MUD). Pacchetto Python
installabile: backend [pachifast](https://pypi.org/project/pachifast/) (FastAPI) + frontend Quasar (Vue 3 + TypeScript)
gia' buildato e incluso, con il comando `pachimudeditor`.

Il core e' generico: i mondi (MUD) arrivano da **adapter**, pacchetti Python separati nello stesso monorepo (`adapters/`),
scoperti con gli entry point `pachimudeditor.adapters` e installabili come *extras*. Per il mondo pachimud l'adapter legge
e scrive il database del server di gioco (`database_url` del mondo, o quello del suo `pachimud.yaml`) con SQLAlchemy,
senza importare il pacchetto `pachimud`; gli utenti dell'editor stanno in un DB SEPARATO, nella *cartella di lavoro*.

- `src/pachimudeditor/` il core (wheel `pachimudeditor`): `app.py` (factory), `modules.py` (moduli pachifast), `apps/`
  (zone, stanze, mob, oggetti, meta, conversione), `common/`, `sdk.py` (API pubblica per gli adapter), `cli/`, `static/` (SPA buildata, git-ignored).
- `adapters/` un pacchetto per adapter, ciascuno con il proprio `pyproject.toml` (uv workspace):
  `pachimud/`, `basedmud/` (con `rom_lib`), `dikumod/` (con `dikumod_lib`), `mapping/` (YAML di mappatura, con gli esempi).
- `frontend/` sorgenti Quasar su `@ilpachi/pachifastquasar`; `e2e/` test Playwright; `tests/` suite pytest (`tests/core/` non richiede adapter).
- Contratto API in `docs/backend/`; piu' MUD tramite adapter (`X-World`, `/api/worlds`) e come scriverne uno: `docs/adapters/index.md`.

Documentazione completa (guida, backend, adapter, formati): sito MkDocs in `docs/` (`uv run --group docs mkdocs serve`);
rilasci e versionamento: `RELEASING.md`.

## Installazione e uso

```bash
uv tool install 'pachimudeditor[all]'  # o solo gli adapter che servono: 'pachimudeditor[dikumod,basedmud]'
pachimudeditor adapters list                        # adapter installati e come aggiungere gli altri
pachimudeditor init --workdir ~/pachimudeditor     # .env, pachimudeditor.yaml, DB auth + migration, primo superuser
$EDITOR ~/pachimudeditor/pachimudeditor.yaml      # webeditor_worlds: nessun mondo e' implicito (esempi commentati per ogni kind)
pachimudeditor serve --workdir ~/pachimudeditor --open     # http://127.0.0.1:8123
```

### Adapter (kind di mondo) ed extras

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
`pachifast` si prende da PyPI. Adapter di terzi: `docs/adapters/index.md` ("Scrivere un adapter esterno").
Senza nessun mondo configurato il server parte lo stesso (`/api/worlds` vuoto) e la UI mostra la pagina
"Nessun mondo configurato" con le istruzioni.

### Comandi

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

### Configurazione

Priorita': variabili d'ambiente > `.env` della cartella > `pachimudeditor.yaml` > default.

- `pachimudeditor.yaml` e' il file YAML di pachifast (sezioni `server`, `app`, `auth`, `events`; il CLI imposta
  `PACHIFAST_CONFIG_FILE`). Chiavi del webeditor: `webeditor_worlds`, `webeditor_default_world`,
  `webeditor_convert_journal_dir`, `config_path` (dentro il mondo pachimud). Segreti (`PACHIFAST_SECRET_KEY`, URL con password) solo in `.env`.
- Mondi: `WEBEDITOR_WORLDS` (JSON) e `WEBEDITOR_DEFAULT_WORLD`, con alias `PACHIMUDEDITOR_WORLDS` /
  `PACHIMUDEDITOR_DEFAULT_WORLD` (i `WEBEDITOR_*` hanno la precedenza).
- Mondo pachimud (`kind: pachimud`), parametri in `params`:

  ```yaml
  webeditor_worlds:
    - id: pachimud
      kind: pachimud
      name: Pachimud
      params:
        database_url: sqlite+aiosqlite:////percorso/a/pachimud/pachimud.db   # URL SQLAlchemy async
        definitions_path: /percorso/a/pachimud/definitions                    # races/, classes/ (e zones/)
        # config_path: /percorso/a/pachimud/pachimud.yaml   # facoltativo: ne legge database_url/definition_path
  ```

  I path SQLite/`definitions_path` relativi si risolvono rispetto alla cartella di lavoro; `config_path` (il `pachimud.yaml`
  del game server) fornisce i valori mancanti e i suoi path relativi si risolvono rispetto alla sua cartella; i parametri
  espliciti vincono. Ripiego: senza `database_url` e `config_path`, la variabile `PACHIMUD_CONFIG_PATH`. All'avvio (e con
  `pachimudeditor worlds check`) si verifica la revisione alembic del database: revisione ignota o colonne assenti sono
  avvisi, e le funzioni collegate (es. `race_id` dei mob) si disattivano; dettagli in `docs/adapters/index.md`.
- Il DB dell'editor (utenti, ecc.) e' il DB di autenticazione di pachifast, SEPARATO dai database dei MUD: le
  connessioni ai MUD le gestiscono solo gli adapter.
- DB auth e migration: `init` genera `migrations/auth/` e `project_modules.py` NELLA cartella di lavoro (pachifast
  li cerca li') e applica `upgrade head`; funziona da un wheel pulito perche' le tabelle sono quelle del core pachifast.
  Dopo un aggiornamento di pachifast con modifiche allo schema: `cd <workdir> && pachifast migrations revision
  "..." --target-name auth --autogenerate && pachifast migrations upgrade --target-name auth`.

La SPA usa path assoluti (`/assets/...`): va servita dalla radice del dominio (reverse proxy senza prefisso).
Unit systemd di esempio: `pachimudeditor.service`.

## Licenza

MIT, vedi il file `LICENSE` (copyright (c) 2026 IlPachi). Ogni adapter ha il proprio `LICENSE`, identico.

## Sviluppo

```bash
uv sync --all-packages                   # workspace: core + tutti gli adapter editabili; il gruppo dev porta pytest
(cd frontend && pnpm install)
uv run pachimudeditor init --workdir .   # la cartella del repo e' anche la cartella di lavoro di sviluppo
uv run pachimudeditor serve --workdir . --reload     # API su :8123; oppure `uv run pachifast dev` (project_modules.py)
cd frontend && pnpm dev                  # app su http://localhost:9010, proxy /api -> :8123 (QCLI_PROXY_TARGET); serve auth.refresh_allowed_origins con l'origine :9010 (vedi example yaml)
uv run pachimudeditor build-frontend     # SPA -> src/pachimudeditor/static (serve per `serve` senza pnpm dev e per gli e2e)
```

Nessun checkout del MUD pachimud serve per sviluppare o testare: i modelli del DB di gioco sono copiati nell'adapter (`game_models/`) e le definizioni di esempio in `tests/fixtures/pachimud_definitions/`. Il confronto opzionale con il MUD vero gira solo con `PACHIMUD_GAME_ROOT=<checkout>` (vedi `docs/contributing.md`).

I test che usano dati reali di basedmud li cercano nel checkout fratello `../basedmud` (override con `BASEDMUD_AREA_DIR`, `ROM_AREA_DIR`, `E2E_BASEDMUD`). I dati reali del **Diku Modificato** non hanno nessun default: i test pytest leggono solo `DIKUMOD_ROOT` (una cartella con `dikumod/lib` e `dikumod2/lib`; prefisso dei file dati `dikumoddata`, o `DIKUMOD_PREFIX`) e gli e2e solo `E2E_DIKUMOD` (una cartella `lib/`; prefisso `E2E_DIKUMOD_PREFIX`); se non sono impostate (o non esistono) i test pytest marcati `real_dikumod`/`real_rom` vengono saltati (gli altri girano su mondi sintetici, vedi `docs/contributing.md`) e i mondi `dikumod*` non compaiono negli e2e. Per gli altri dati mancanti i test pytest si saltano, mentre gli e2e che li copiano falliscono con un errore esplicito.
Per lavorare sui propri mondi copia `pachimudeditor.example.yaml` in `pachimudeditor.yaml` o `pachimudeditor.local.yaml` (entrambi ignorati da git) e con il `.local` imposta `PACHIFAST_CONFIG_FILE=pachimudeditor.local.yaml` nel `.env`.

## Test

Entrambe le suite lavorano solo su database **temporanei** (mai `pachimud.db`).

```bash
uv run pytest -q                          # API in-process (httpx + ASGI) su DB temporanei creati con i modelli copiati del gioco; nessun checkout del MUD
uv run pytest tests/core -q               # solo il core: nessun adapter richiesto (adapter fittizi con entry point sintetici)
(cd frontend && pnpm run typecheck)
cd e2e && pnpm install && pnpm test       # lancia un Chrome headless proprio (profilo temporaneo); richiede la SPA in static/
```

Dettagli in `e2e/README.md`.

## Build e distribuzione (manuale: nulla viene pubblicato dagli script)

```bash
scripts/build_package.sh                  # build-frontend + uv build di core e adapter -> dist/*.whl e *.tar.gz
scripts/build_package.sh --only dikumod       # un solo pacchetto (core | pachimud | basedmud | dikumod | mapping)
env -u UV_PUBLISH_INDEX uv publish --publish-url https://<host>/<percorso-upload> --username <utente> dist/*   # a mano
```

Ogni adapter e' un wheel a se' (`pachimudeditor_adapter_<kind>-<ver>-py3-none-any.whl`); gli extras del core puntano ai loro
nomi su PyPI (le `[tool.uv.sources]` del workspace servono solo allo sviluppo e non entrano nel wheel). Credenziali di upload in
`UV_PUBLISH_USERNAME`/`UV_PUBLISH_PASSWORD`, mai nel repo.
