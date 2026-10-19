# Webeditor pachimud — backend (pachifast)

Backend [pachifast](https://pypi.org/project/pachifast/) del webeditor (pacchetto `pachimudeditor`, sorgenti in
`src/pachimudeditor/`): per il mondo pachimud legge/scrive il database del game server indicato dai parametri del mondo (`database_url`,
`definitions_path`, `config_path` opzionale: vedi [adapter](../adapters/index.md), sezione "Adapter pachimud") riflettendone le tabelle con
SQLAlchemy: il pacchetto `pachimud` non e' importato. Il database di autenticazione (`db.sqlite3`, utenti) e' separato e
SUO dell'editor: le tabelle di gioco sono gestite da alembic nel repo principale (qui non ci sono migration per esse; l'editor
ne controlla solo la revisione).

Contratto per il frontend: [contratto API](contract.md).

## Avvio

```bash
uv sync
uv run pachimudeditor init --workdir .     # (sviluppo: cartella del repo) .env, migration auth, primo superuser
uv run pachimudeditor serve --workdir . --reload    # porta 8123 (pachimudeditor.yaml); docs su /docs
```

Produzione: vedi `README.md` (wheel installato, `pachimudeditor serve`). La SPA e' servita se esiste
`src/pachimudeditor/static` (`pachimudeditor build-frontend`).

Sicurezza: `PACHIFAST_SECRET_KEY` (almeno 32 caratteri) e' obbligatoria anche in debug: pachifast rifiuta l'avvio senza (verificato in `pachifast.config.settings`), quindi `serve` non fa un controllo proprio.

## Utenti

Ogni route `/api/...` richiede un token (`POST /api/auth/token`, form `username`/`password`).
L'auto-registrazione è disattivata: nuovi utenti con

```bash
uv run pachimudeditor users create <nome> --superuser     # chiede la password
```

## Integrita' dei dati (regole lato server)

- Script di reset (`PUT /zones/{id}/reset-commands`): validazione per tipo di comando (`src/pachimudeditor/apps/zones/reset_script.py`),
  vnum referenziati devono esistere; `POST .../reset-commands/validate` riporta errori e warning senza salvare.
- Il cambio di `vnum` di stanza/mob/oggetto e' rifiutato (409 `*.vnum_in_use`) se referenziato da reset o, per gli
  oggetti, da `Exit.key_vnum` (`pachimudeditor_adapter_pachimud/editor/reset_usage.py`); la delete e' rifiutata anche con istanze vive
  (`pachimudeditor_adapter_pachimud/editor/instances.py`) o se l'oggetto e' chiave di un'uscita. Le uscite entranti non bloccano la delete di una stanza.
- I body di PUT estendono `common/editor/schemas.py::PatchModel` (no `null` su colonne NOT NULL; `nullable_fields` per le eccezioni).
- Clone zona: il range vnum non si copia (0-0 o `bottomVnum`/`topVnum` espliciti, 409 se si sovrappone).
- Elenco codici e payload: [contratto API](contract.md).

## Mondi (adapter)

Il backend serve piu' MUD tramite `WorldAdapter` (`X-World`/`?world=`), vedi [adapter](../adapters/index.md). Oltre a pachimud (DB) ci sono
`kind: basedmud` (file `.are` di basedmud/ROM, libreria `rom_lib`, pacchetto `adapters/basedmud/`) e `kind: dikumod` (file dati di
"Diku Modificato", libreria `dikumod_lib`, pacchetto `adapters/dikumod/`). In `pachimudeditor.yaml`:

```yaml
webeditor_worlds:
  - {id: pachimud, kind: pachimud, params: {database_url: "sqlite+aiosqlite:////percorso/pachimud.db", definitions_path: /percorso/definitions}}
  - {id: basedmud, kind: basedmud, name: BasedMud, path: /percorso/basedmud, read_only: false}
  - {id: dikumod2, kind: dikumod, name: Diku Modificato, path: /percorso/dikumod2, params: {variant: dikumod2}}   # read_only: true di default
```

**`kind: dikumod` e' in sola lettura se `read_only` non e' scritto**: i file monolitici sono fragili (il gioco legge mob e
oggetti per offset di byte: scrivere con il gioco acceso lo rompe) e le scritture vanno abilitate esplicitamente con
`read_only: false`, a gioco fermo. Le librerie (`pachimudeditor_adapter_basedmud.rom_lib`, `pachimudeditor_adapter_dikumod.dikumod_lib`) hanno un README e test propri
(`tests/rom_lib`, `tests/dikumod_lib`).

I test di BasedMud (`tests/basedmud`) e di Diku Modificato (`tests/dikumod_lib`, `tests/dikumod`) lavorano su copie temporanee dei dati reali
(`basedmud/area`, percorso sovrascrivibile con `BASEDMUD_AREA_DIR`; per il Diku Modificato solo `DIKUMOD_ROOT`, cartella con `dikumod/lib` e `dikumod2/lib`, prefisso dei file con `DIKUMOD_PREFIX`: senza la variabile quei test si saltano) e verificano a
fine sessione, con gli hash, che gli originali siano intatti. `uv run pytest tests/dikumod_lib -s` stampa le statistiche
(conteggi, mob corrotti per categoria, zone viste dal loader C).

## Test automatici

`uv run pytest` esegue la suite in `tests/` (httpx con trasporto ASGI) contro DB di gioco e di
autenticazione temporanei seminati da `tests/support/stack.py` (usa il pacchetto `pachimud`, dipendenza di solo
sviluppo, per creare lo schema e i dati di prova); non tocca `pachimud.db`. I test di equivalenza con il gioco sono in
`tests/test_equivalence.py` (saltati senza `pachimud`). I test e2e
del browser sono in `../e2e` (vedi `../README.md`).

## Test (smoke, sola lettura)

Con il server avviato e un utente di test:

```bash
SMOKE_USER=<nome> SMOKE_PASSWORD=<password> uv run python scripts/smoke.py [http://127.0.0.1:8123]
```

Per provare le scritture usa una copia di `pachimud.db` e un `pachimud.yaml` copiato che la
punti (`params.database_url` del mondo); per non toccare gli utenti veri usa un db di
autenticazione temporaneo con `PACHIFAST_AUTH_DATABASE_URL`. Controllo dei cataloghi messaggi:
`uv run pachifast locale check`.
