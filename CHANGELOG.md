# Changelog

Un solo file per i cinque pacchetti. Le release sono sezioni `## <pacchetto> X.Y.Z - data` (vedi Rilasci); le modifiche in corso stanno sotto "Non rilasciato".

## Non rilasciato

- SDK 1.4 (additivo): **scrittura** dei giocatori dei MUD su file (L3). `PlayersAdapter` ottiene `update_player`, `add_player_item`, `update_player_item`, `remove_player_item` (default 409 `world.capability_missing`) e i DTO neutri `PlayerWriteOptions` (`revision`, `confirm_server_running`), `PlayerPatch` (`details`/`lists`, patch parziale), `PlayerItemAdd`, `PlayerItemUpdate`; capability `supports_player_write` e `supports_player_inventory_write`; `PlayerSummary.revision`, `PlayerInventory.revision` e `PlayersInfo.wear_slots`. Rotte: `PATCH /api/world/players/{id}`, `POST /{id}/inventory/items`, `PATCH|DELETE /{id}/inventory/items/{itemId}`. Il core controlla `read_only` (409 `world.read_only`), la capability, l'id e la **conferma del server acceso** (`serverRunning: true` richiede `confirmServerRunning`, altrimenti 409 `worldplayers.server_running`); l'adapter la concorrenza (`revision` -> 409 `worldplayers.conflict`), la validazione (422 `worldplayers.invalid_value`, 409 `worldplayers.item_invalid`/`file_unwritable`, 404 `worldplayers.unknown_object`/`item_not_found`), la copia `<file>.bak` e la scrittura atomica. `SDK_VERSION` 1.4, `sdk_version` di dikumod 1.4. Docs: `backend/contract-players-files.md`, `adapters/sdk.md`.
- dikumod: writer binario simmetrico al parser (`dikumod_lib/players_write.py`): cambia solo i campi richiesti sui byte attuali (nessuna modifica = file identico, password e byte sconosciuti intatti, mai scritta), validazione di ogni valore (tipo, intervallo, lunghezza dei campi char, latin-1, enum, flag per nome); `RentEditor` per il rent (record da 592 byte, preordine e profondita' come `obj_store_to_char`, slot unici, al massimo 200 oggetti e 60 livelli, `owner` e `total_cost`/`gold_left` coerenti, oggetti dal prototipo con `timer`/`bitvector` 0). Un rent incoerente o di un altro proprietario non si modifica. Backup `players/<nome>.dat.bak` e `rent/<nome>.bak` (una generazione, stessi permessi): **il gioco legge ogni file non nascosto di `players/`, sposta il `.bak` fuori prima del riavvio** (vedi `docs/adapters/dikumod.md`). Il lettore non cambia comportamento. Formato: `docs/formats/dikumod.md`.
- Frontend `/player-files`: modifica dei campi (editor per tipo guidato da `PlayersInfo`, tabelle abilita'/effetti come JSON, salvataggio con `revision`), avviso e conferma obbligatoria se il server e' acceso, gestione di conflitto e valori non validi; inventario con aggiungi (ricerca nel catalogo oggetti per nome/vnum, slot o contenitore), cambio slot e rimozione con conferma. Mondo `read_only` o senza le capability: nessun controllo di modifica. it/en.
- Test: writer (round-trip identico, ogni campo, valori invalidi, file corrotti, rent), HTTP (permessi, `read_only`, server acceso con/senza conferma, conflitto, `.bak`, password mai nelle risposte/log, id malevoli, symlink), dati reali solo su copie temporanee (round-trip di ogni giocatore e rent reale), E2E (modifica, conflitto, server acceso, inventario).

- Docs (solo specifica, nessun codice): canale di controllo live tra l'editor e un MUD in esecuzione. `backend/live-control-protocol.md` (protocollo `livectl`: socket Unix + righe JSON, handshake con capability discovery, token/allowlist/limiti/audit, comandi `ping info who player.get player.set zone.list zone.reset load.mob load.obj echo`, rischi e domande aperte) e `adapters/dikumod-live.md` (punti di innesto nel sorgente C di Diku Modificato, mappatura sulle funzioni del gioco, campi modificabili, differenze dikumod/dikumod2).
- Richiede `pachifast>=0.19.0`: il limite delle rotte costose usa `rate_limit(default=60, ...)` al posto della modifica delle impostazioni a runtime (`apply_rate_limit_defaults` rimossa). Stesso comportamento: `rate_limit.default: 0` spegne il limite.
- SDK 1.3 (additivo): giocatori dei MUD su file in **sola lettura** (L1 elenco, L2 dettaglio + inventario/equipaggiamento). Mixin opzionale `PlayersAdapter` con DTO neutri (`PlayerSummary`, `PlayerDetail`, `PlayerInventory`, `PlayerItem`: id opaco, `hasPassword` booleano, mai l'hash, `extra` dichiarativo), descrittore `PlayersInfo` (colonne, campi e tabelle del dettaglio con etichette i18n, `onlinePolicy`) e capability `supports_player_records` / `supports_player_inventory`. Rotte neutre nel core `GET /api/world/players/{info,status,,{id},{id}/inventory}` (X-World, 409 `world.capability_missing`, 404 `worldplayers.not_found`, id validato contro il path traversal); `/api/players` di pachimud invariato. Docs: `backend/contract-players-files.md`, `adapters/sdk.md`.
- dikumod: parser binario (`dikumod_lib/players.py`: `char_file_u` 3036 byte e rent 40 + n x 592 con offset espliciti little-endian, verificati con g++ `offsetof`) e mixin `PlayersMixin`: elenco di `lib/players/*.dat`, dettaglio (abilita', effetti, punti, stato), inventario con slot, annidamento e prototipi del mondo. File troncati/corrotti, `number` > 200, nomi non validi e symlink fuori cartella diventano `problem` (mai 500); nessuna scrittura, la password non esce mai (solo `hasPassword`). Rilevamento «server acceso» best effort (processo con cwd = `lib/` e socket) + avviso generico. Formato in `docs/formats/dikumod.md`.
- Frontend: nuova pagina `/player-files` («Giocatori», solo con la capability) guidata dal descrittore: colonne dichiarate con paginazione/ordinamento/ricerca lato server, banner di avviso sola lettura/server acceso, dialog di dettaglio (`PachiDialog`) a sezioni con tabelle e inventario; it/en. La pagina `/players` di pachimud non cambia.
- Test: fixture sintetiche `tests/support/dikumod_players.py` (`struct.pack`), test del parser/rent (anche corrotti), HTTP, guardie (sola lettura, nessun campo password, nessuna password in risposte e log), dati reali solo su copie in cartella temporanea con la password azzerata (con `DIKUMOD_ROOT`), nuovo E2E `playerfiles.test.ts` (lo stack E2E sostituisce players/ e rent/ con giocatori sintetici).

## pachimudeditor-adapter-pachimud 0.1.1 - 2026-10-20

- Richiede `pachimudeditor>=0.1.1`: le rotte costose (import di zone) usano `heavy_rate_limit` dell'SDK del core (limite di richieste di pachifast 0.18, codice `api.rate_limited`). Nessun altro cambio.

## pachimudeditor 0.1.1 - 2026-10-20

- Dipendenze: `pachifast>=0.18.0`. Il limite di richieste fatto in casa (`http_guard.py`, middleware con contatore per IP) e' sostituito dal `rate_limit` di pachifast come dipendenza sulle rotte `POST /api/convert/preview|run` e `POST /api/transfer/zones/import` (`heavy_rate_limit()` in `common/rate_limit.py`, esportata dall'SDK): conteggio per utente autenticato (ripiego IP), scope `heavy`, header `X-RateLimit-*`. Configurazione con `rate_limit.default`/`rate_limit.window_seconds` (env `PACHIFAST_RATE_LIMIT_DEFAULT`/`_WINDOW_SECONDS`), default dell'editor 60/60 s; `WEBEDITOR_HEAVY_RATE_LIMIT`/`_WINDOW` restano alias deprecati. Cambio: il codice del 429 e' ora `api.rate_limited` (era `auth.rate_limited`). Gli header di sicurezza restano nel middleware dell'editor.
- Frontend: `@ilpachi/pachifastquasar` `^0.1.6`. Il proxy di sviluppo `/api` riscrive anche l'`Origin` sul target: in `pnpm dev` (SPA su :9010) il refresh in cookie mode passa il controllo CSRF senza `refresh_allowed_origins`, quindi e' tolto da `pachimudeditor.example.yaml` e dalle docs (resta documentato solo il caso SPA/API su origini diverse in produzione). Provato davvero: `pnpm dev` + backend su altra porta senza `refresh_allowed_origins`, login e ricarica con Chrome headless, refresh 200 e nessun `403 auth.csrf_rejected`.
- Dipendenze: `pachifast>=0.17.1`. Un refresh via cookie ripetuto entro `refresh_reuse_grace_seconds` col token appena ruotato risponde 200 con nuovo `Set-Cookie` invece di 401: `goto` seguito subito da `reload` non perde piu' la sessione. Nuovo E2E in `session.test.ts` e rimosse le attese `networkidle` che servivano solo da mitigazione (`goto`, cambi di mondo).- Sicurezza: refresh token in cookie `HttpOnly` (pachifast 0.17.0, `@ilpachi/pachifastquasar` 0.1.5). Il backend usa `auth.refresh_mode=cookie` per default (esplicito in yaml/env vince; `init` e `pachimudeditor.example.yaml` lo scrivono; l'example elenca anche l'origine del dev server :9010 in `refresh_allowed_origins`, perche' il proxy di Quasar riscrive l'Host ma non l'Origin e senza il refresh risponde 403), la SPA `auth: { refreshMode: 'cookie' }`: niente token in `localStorage`, access token in memoria, sessione condivisa tra schede. Nuovi E2E in `auth.test.ts` (nessun token in storage, cookie non leggibile da JS, ricarica, due schede, logout propagato, `403 auth.csrf_rejected` senza `X-Pachi-Auth`) e test pytest del default. Docs: `security.md` (decisione sul token risolta, rischio residuo XSS) e `configuration.md`.
- E2E: la suite lancia un proprio Chrome headless con profilo temporaneo (`E2E_CHROME_PATH` per scegliere l'eseguibile) invece di collegarsi al Chromium dell'utente sulla porta 9222, che non viene piu' toccato; `E2E_CDP_URL` esplicita mantiene il vecchio collegamento. Intera suite (116 test) verde in headless senza correzioni ai test.
- Frontend: i quattro `q-dialog` nudi (istanze mob/oggetto, inventario e selettore dei giocatori) usano `PachiDialog` di `@ilpachi/pachi-kit/dialog`: `aria-labelledby` sul titolo, pulsante di chiusura con `aria-label`, Esc come prima; i pulsanti di azione restano nello slot `actions`. Nuovo E2E in `instances.test.ts` (aria-labelledby punta al titolo, Esc chiude). Il `@hide` va scritto `onDialogHide()` perche' `PachiDialog` emette il motivo come stringa.
- Dipendenze frontend (Dependabot): `@types/node` 26.6.5, `typescript` 6.0.3 (typecheck, build ed E2E verdi senza modifiche al codice), `esbuild` 0.28.2.
- Sicurezza: middleware `common/http_guard.py` con `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` e CSP (stretta per API/SPA, con jsDelivr solo per `/docs*`); limite di richieste per indirizzo su conversioni e import zone (`WEBEDITOR_HEAVY_RATE_LIMIT`/`_WINDOW`, default 60/60 s, 429 `auth.rate_limited`; pachifast ha un limite solo per l'autenticazione). Nuova pagina `docs/guide/security.md` con le due decisioni aperte (permessi per utente, token in `localStorage`). Nuovi test: header e limite, fuzz di testi ostili su tutte le rotte da OpenAPI (mai 5xx), import in mondo `read_only` (409), `atomic_write_bytes` con `chown` negato, E2E `security` (SPA e `/docs` senza violazioni CSP) e Applica disabilitato in sola lettura.
- Frontend: la mappa stanze con `?zoneId=` lanciava due caricamenti sovrapposti (zona di default e zona del deep-link): una risposta in ritardo poteva sovrascrivere la mappa (test E2E instabile). Ora vale solo l'ultimo caricamento.
- Docs: `RELEASING.md` con la checklist del primo rilascio su PyPI; rimosso `docs/assets/logo.png` non referenziato.
- Conversione: l'anteprima (e il run) validano i testi sull'arrivo prima di scrivere: nuovo hook opzionale `WorldAdapter.check_texts(texts, *, zone_id)` (default: niente), implementato da basedmud (encoding del `.are` esistente, NUL) e dikumod (latin-1); emoji verso un arrivo che non le codifica = 422 `basedmud.unencodable_text` / `dikumod.unencodable_text` invece di anteprima ok e scrittura fallita. `vnumPolicy.offset` limitato a +-(2^31-1) (422). Ruff attiva anche `D` e `ANN`.
- basedmud: i token liberi scritti nel `.are` (size, material, startPos, defaultPos, damType, special, itemType, condition, values, trigger e word dei flagRemovals, commenti, intestazione) non ammettono spazi, a capo ne' NUL: prima `"x\n#0\n#999"` troncava il file al reload (mob 986 -> 975) e il PUT rispondeva 404 dopo aver scritto. Ora 422 `basedmud.unsafe_text`; in piu' il testo generato viene riletto prima del replace (sequenza dei record invariata) e tutti i file di una scrittura sono verificati prima di scriverne uno. Testo non codificabile nell'encoding del file (emoji): 422 `basedmud.unencodable_text`.
- dikumod: testo non rappresentabile in latin-1 (emoji, `€`): 422 `dikumod.unencodable_text` invece di 500, verificato prima di scrivere il primo file. Documentato che `#N` e' ammesso in stanze e zone (non indicizzate per riga) e vietato solo in `.mob`/`.obj`; `docs/guide/configuration.md` espone il default `read_only` per tipo di mondo.
- SDK 1.2: `pachimudeditor.sdk.atomic_write_bytes` (risolve i symlink e scrive sul target reale, conserva permessi e, se possibile, proprietario/gruppo, `fsync` di file e cartella, pulizia del temporaneo). Sostituisce le tre copie di basedmud, dikumod e mapping; `sdk_version` dei tre adapter a `1.2`. `pachimudeditor.sdk` diventa un pacchetto (`sdk/__init__.py`, `sdk/files.py`), stessi import.
- Metadati PyPI dei 5 pacchetti: `[project.urls]` (Homepage, Documentation, Repository, Issues, Changelog), `keywords` e classificatori (Python 3.14, OS Independent, Topic MUD, Framework FastAPI per il core, Environment Plugins per gli adapter); `Private :: Do Not Upload` resta. La sdist del core include `mkdocs.yml` e `overrides/` (con `docs/` e `scripts/mkdocs_hooks.py` basta per `mkdocs build --strict`).
- Docs: l'esempio di adapter esterno in `docs/adapters/sdk.md` e' completo (import di `AppModule` da `pachifast`, `adapter.py` minimo provato in un venv pulito con `adapters list` e `worlds check`), la regola minor/major rimanda alla costante `SDK_VERSION` e c'e' il riepilogo degli helper SDK.
- Test: coperti `common/adapters/lifecycle.py` (0% -> 100%), `init` (28% -> 100%), `build-frontend` (38% -> 100%), `worlds` (49% -> 98%) e `serve` (51% -> 100%) con test in `tests/core/` (cartelle temporanee, nessuna rete, uvicorn e pnpm sostituiti).
- pachimud (transfer): piu' zip nello stesso upload danno 422 `transfer.multiple_zones` invece di 500 (contatore gruppi condiviso); limiti cumulativi su byte, file (10) e voci (200), 2 MB per ogni YAML e 5000 record per file; parsing YAML fuori dal loop e query `IN` a blocchi (niente piu' blocchi del server ne' `too many SQL variables`).
- pachimud: id/page/pageSize oltre i 64 bit e vnum oltre 2^31-1 rispondono 422 (`world.value_out_of_range` / validazione) invece di 500 o di accettare vnum assurdi. `/api/convert/pairs` ora segnala `same_world` come `/run` quando due id puntano agli stessi dati (prima `target_read_only`).
- basedmud e mapping: una scrittura fallita a meta' (es. `extra` invalido dopo la mutazione dei campi) non lascia piu' la cache sporca: `writing()` invalida la cache come dikumod, quindi il valore scartato non resta in memoria ne' finisce su disco al salvataggio successivo.
- basedmud (`rom_lib`) e `rom.yaml` (mapping): modificare l'intestazione di una zona (`#AREA`/`#AREADATA`) non aggiunge piu' una riga vuota a ogni salvataggio.
- Test: i dati reali dei MUD sono opzionali. Mondi sintetici versionati (`tests/support/synthetic_worlds.py`) fanno girare in CI scritture, round trip, mutazioni, conversione e contratto; i test su contenuti precisi dei dati reali sono marcati `real_rom`/`real_dikumod`. Su clone pulito: 449 passati e 210 saltati prima, 627 passati e 107 saltati dopo. La CI fallisce oltre `MAX_SKIPPED`; `DIKUMOD_ROOT`, `DIKUMOD_PREFIX`, `BASEDMUD_AREA_DIR` documentati in `docs/contributing.md`.
- Docs: `DOCS_SITE_URL` fisso `https://pachimudeditor.ilpachi.it/` (canonical e sitemap erano `http://`). Dependabot anche per `/e2e`; e2e senza `waitForTimeout` fissi in `instances` e `players`.

- pachimud: `read_only` ora e' applicato anche a players, instances e content (409 `world.read_only` su ogni POST/PUT/PATCH/DELETE, prima passavano e scrivevano su DB/YAML). Le capability non cambiano (le GET restano disponibili).
- pachimud: il 503 `world.unavailable` non espone piu' percorso del DB e messaggi del driver (dettaglio solo nel log del server; `worlds check` lo mostra ancora). Il messaggio localizzato non ha piu' il segnaposto `{detail}`.
- pachimud: documentato che i range vnum di zona sono consultivi (nessun `vnum_out_of_range` in scrittura, solo nel controllo di integrita').

- Frontend: in un mondo `read_only` pachimud ora sono disabilitate anche le azioni di scrittura di istanze (nuovo/modifica/elimina), giocatori (account: nuovo, email, password, ban, elimina; personaggi: modifica, teletrasporto, elimina; inventario: aggiungi, slot, rimuovi), razze/classi (nuovo, modifica, disattiva, elimina) e l'applicazione dell'import in Trasferimento. I dialoghi di prompt (es. "Nuovo account") e di istanza si chiudono con Esc.
- Frontend: nome app e `<title>` "Pachimud Editor" (prima "Pachimud Webeditor"; la barra mostrava il default della libreria). Sotto 600 px la barra e' adattiva (nome nascosto, selettore che si restringe, lucchetto al posto del badge "Sola lettura", badge `params` visibili da 1024 px) e le tabelle di `/convert` scorrono in orizzontale invece di essere tagliate.
- Frontend: `aria-label` su tutti i pulsanti solo-icona (comandi di reset zone, clone, suggerimento vnum, azioni di razze/classi, controlli dei grafici) e stringhe `errors.http.*` (it/en) mancanti: le tabelle mostrano "Non hai i permessi per questa operazione." e simili invece di `Forbidden` / `Error: 403 - Forbidden`.
- E2E: mondo `pachimud-ro` (stesso DB, sola lettura) e test `readonly`, `errors`, `a11y` (375 px).

- Frontend: il selettore di mondo mostra come badge i `params` non vuoti del mondo attivo (es. "Prefisso dati", "Variante"; etichette i18n it/en).

- `AdapterInfo.params` (dict informativo, default vuoto) in `GET /api/worlds`; dikumod espone `variant` e `data_prefix`. `SDK_VERSION` 1.1 (additivo, compatibile con gli adapter 1.0).

- Licenza MIT (espressione SPDX `license = "MIT"` e `LICENSE` in `pachimudeditor` e nei 4 adapter `-pachimud`, `-basedmud`, `-dikumod`, `-mapping`); email rimossa dagli `authors`; path personali sostituiti da segnaposto e default relativi ai checkout fratelli (`../basedmud`). `pachimudeditor.example.yaml` e' il template generico (la versione personale va in `pachimudeditor.yaml` o `pachimudeditor.local.yaml`, ignorati). Il classificatore `Private :: Do Not Upload` resta finche' non si decide di pubblicare su PyPI.

- Il progetto vive in un repository proprio (storia di `webeditor2/` e `pachimudeditor/` mantenuta). Il gioco `pachimud` non e' una dipendenza del progetto (nemmeno di sviluppo) e non serve nessun checkout: i modelli SQLAlchemy del DB di gioco sono copiati in `adapters/pachimud/.../game_models/` (usati da test, seed e2e e script) e le definizioni di esempio in `tests/fixtures/pachimud_definitions/`. Il confronto con il MUD vero e' opzionale (`tests/test_game_compat.py`, solo con `PACHIMUD_GAME_ROOT`). Un test AST vieta ogni `import pachimud` nel repo.

- Il core rifiuta un plugin con `sdk_version` di major diversa da `SDK_VERSION` (kind in errore, non crash); i 4 adapter dichiarano `sdk_version="1.0"`.

### Adapter come pacchetti separati (plugin)

- Il monorepo ora produce piu' pacchetti: `pachimudeditor` (core generico) e `pachimudeditor-adapter-pachimud`, `-basedmud`,
  `-dikumod`, `-mapping` (cartella `adapters/`, uv workspace). Il core non importa mai gli adapter: li scopre con gli entry point
  del gruppo `pachimudeditor.adapters` (`AdapterPlugin`: kind, factory, moduli API, sapore di conversione, validazione,
  esempio di config) e li espone come extras (`pachimudeditor[pachimud|basedmud|dikumod|mapping|all]`).
- Caricamento lazy: un kind non configurato non importa nulla di pesante; i moduli API di un adapter (es. world/players/
  instances/transfer/content del gioco) si registrano solo se esiste un mondo di quel kind. Un plugin che non si importa e'
  segnalato (log, `adapters list`) senza far cadere il core; un mondo con kind non installato da' un errore che indica
  l'extra da installare.
- Nuovo `pachimudeditor.sdk`: API pubblica per gli adapter esterni (`SDK_VERSION` 1.0); verificata da un test AST
  (`tests/core/test_boundaries.py`: il core non importa adapter, gli adapter usano solo l'API pubblica).
- Spostati negli adapter: SQLAlchemy riflessivo, moduli e helper del gioco (`apps/{world,players,instances,transfer,content}`,
  `common/editor/{crud,db,reset_usage,instances,pagination}`), messaggi `world.not_pachimud|unavailable|field_unsupported` e
  `common.editor.*`, `rom_lib` (ex `adapters_rom_lib`), `dikumod_lib` (ex `adapters_dikumod_lib`), esempi e schema del mapping.
  Il core non dichiara piu' `sqlalchemy`, `aiosqlite`, `argon2-cffi`, `pyyaml`, `ruamel-yaml` (sqlalchemy e aiosqlite restano
  installati perche' li richiede pachifast per il DB di autenticazione).
- Conversione: le regole stanno nell'adapter del mondo (un `Flavor` per kind, `AdapterPlugin.flavor`); nel core restano
  `Flavor`/`ComposedConverter`, helper e tabelle del pivot. Le coppie si compongono dai plugin installati.
- CLI: `pachimudeditor adapters list`; `info`, `worlds list|check` mostrano i kind disponibili e quelli da installare;
  `init` genera un `pachimudeditor.yaml` con l'esempio commentato di ogni adapter installato.
- Test: `tests/core/` gira senza adapter (adapter fittizi con entry point sintetici); lo stack completo richiede gli adapter e `pachimud`.
- `scripts/build_package.sh` costruisce core (con la SPA) e ogni adapter; `create_editor_app(extra_kinds=...)`.

### Mondo pachimud senza il pacchetto del gioco

Il mondo pachimud non dipende piu' dal pacchetto del gioco (`pachimud`): schema-on-read con SQLAlchemy.

- `adapters/pachimud` riscritto: apre il database di gioco indicato dai parametri del mondo
  (`params.database_url`, `params.definitions_path`, `params.config_path` opzionale) con SQLAlchemy async e riflette le
  tabelle reali (`MetaData.reflect`) invece di importare i modelli ORM del gioco. Engine e sessioni sono dell'adapter
  (per mondo, creati al primo uso, chiusi allo spegnimento); i pragma SQLite sono quelli del game server.
- Nessun `import pachimud` in `src/pachimudeditor` (test di scansione AST + processo `python -I` con l'import bloccato),
  niente `sys.path`/`python_path`. Lo schema del DB di prova si crea con i modelli copiati del gioco (`game_models`).
- I moduli `world/players/instances/transfer/content` si registrano quando e' configurato un mondo `kind: pachimud` (senza
  controllo di importabilita') e usano il database del mondo scelto dalla richiesta (`X-World`): `common/editor/db.py` espone
  `SessionDep`/`PachimudDep` che risolvono l'adapter attivo (409 `world.not_pachimud` se il mondo e' di un altro tipo).
  L'API pubblica (rotte, payload, codici) e' invariata.
- Controllo di compatibilita' dello schema: lettura di `alembic_version`, tabella delle revisioni note
  (`64f2026e1334` .. `9d4aa2f29079`) e delle colonne attese. Revisione ignota/colonne assenti: avvisi nel log e in
  `worlds check`; colonne non essenziali assenti (`race_id`, `class_id`, `arg_str`, `heal_rate`, ...) = campi `unsupported` in
  `describe()` (422 `world.field_unsupported` se si scrive un valore non neutro); tabelle opzionali assenti spengono le
  capability collegate; schema incompatibile = 503 `world.unavailable` solo per quel mondo.
- Nuovi codici di errore: `world.not_pachimud`, `world.unavailable`, `world.field_unsupported` (it/en).
- Enum e flag in tabelle dati dell'editor (`common/enums.py`, `adapters/pachimud/race_enums.py`); razze/classi con modelli
  Pydantic propri (`adapters/pachimud/definitions.py`); hash Argon2id con `argon2-cffi` (dipendenza ora dichiarata, come
  `sqlalchemy`, `aiosqlite`, `pyyaml`), identico a quello del gioco.
- Export/import YAML di zona (`adapters/pachimud/transfer/`) riscritto: stessi file e stessa semantica upsert dell'importer del
  gioco (verificata da round-trip sempre attivi e, con `PACHIMUD_GAME_ROOT`, dal confronto con l'importer del MUD).
- Rimossa la logica di `PACHIMUD_CONFIG_PATH` da `common/editor/db.py`; resta come ripiego documentato di `config_path`
  (`adapters/pachimud/params.py`). `pachimudeditor info` non mostra piu' la versione di `pachimud`.
- `worlds check`: per i mondi pachimud mostra revisione e stato dello schema.
- Test: nuova suite `tests/test_equivalence.py` (hash, trasferimento zone, enum/schemi/colonne/revisioni vs gioco, saltata
  senza `pachimud`), `tests/test_bootstrap.py` (nessun import del gioco, app completa con `pachimud` bloccato),
  `tests/test_schema_check.py` (degrado su schemi vecchi/ignoti).

## 0.1.0

Prima versione distribuibile: il webeditor (ex `webeditor2/`) diventa il pacchetto Python `pachimudeditor`.

- Backend pachifast come pacchetto reale (`src/pachimudeditor`: `apps/`, `common/`, `adapters/`,
  `adapters_rom_lib/`, `adapters_dikumod_lib/`), factory `pachimudeditor.app:create_editor_app`, moduli in
  `pachimudeditor.modules`.
- Frontend Quasar buildato e incluso nel wheel (`pachimudeditor/static`), servito dallo stesso processo.
- CLI `pachimudeditor`: `init`, `serve`, `users`, `worlds`, `build-frontend`, `info`, `--version`.
- Cartella di lavoro (`.env`, `pachimudeditor.yaml`, DB di autenticazione, migration) generata da `init`.
- Nessun mondo implicito; `pachimud` (gioco) non e' una dipendenza: mondi pachimud e moduli collegati attivi solo se
  c'e' un mondo `kind: pachimud` (l'adapter non importa il gioco). Config del game server: `config_path` del mondo, `PACHIMUD_CONFIG_PATH` o `pachimud.yaml`
  in cwd; i path relativi si risolvono rispetto alla cartella di quel file.
- Alias `PACHIMUDEDITOR_WORLDS` / `PACHIMUDEDITOR_DEFAULT_WORLD` (restano validi `WEBEDITOR_*`).
