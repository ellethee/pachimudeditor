# Test e2e del webeditor

Test Playwright (`playwright-core`) eseguiti con `node:test` + `tsx`. Si collegano al Chromium **gia'
avviato** con il debugging remoto su `http://localhost:9222` (`chromium.connectOverCDP`): ogni file apre
un nuovo contesto/tab e lo chiude alla fine, senza toccare i tab esistenti.

## Prerequisiti

- Chromium con `--remote-debugging-port=9222` in esecuzione (override: `E2E_CDP_URL`).
- il progetto sincronizzato con il gioco (`uv sync --all-packages` + `uv pip install -e ../pachimud`, checkout fratello) e frontend buildato e copiato nel pacchetto
  (`uv run pachimudeditor build-frontend`, genera `src/pachimudeditor/static`).
- `pnpm install` in questa cartella.

## Uso

```bash
pnpm test                              # setup stack + tutti i test + teardown
pnpm test tests/zones.test.ts          # solo alcuni file
pnpm run stack                         # solo lo stack isolato (Ctrl+C per fermarlo), per prove a mano
E2E_SKIP_STACK=1 pnpm test             # usa uno stack gia' attivo su E2E_BASE_URL (default http://127.0.0.1:8124)
pnpm run typecheck
```

## Stack isolato

`run.ts` (setup/teardown globali, `support/stack.ts`):

1. crea una cartella temporanea in `e2e/.tmp/run-*` con una copia di `definitions/`, DB di gioco
   SQLite seminato (zone 10 e 20, 3 stanze, 2 mob, 2 oggetti, 2 reset) e DB di autenticazione con
   l'utente di test (tramite `tests/support/stack.py`);
2. avvia `uvicorn pachimudeditor.app:create_editor_app --factory` del backend sulla porta **8124**: serve anche il frontend buildato
   (`src/pachimudeditor/static`), quindi e' un unico processo;
3. a fine test lo ferma con il suo **PID esatto** (SIGTERM, poi SIGKILL) e cancella la cartella.

Il mondo `pachimud` ha parametri espliciti (`database_url` e `definitions_path` verso la cartella temporanea; il pacchetto `pachimud` serve solo allo script di seed, mai al server). Il setup copia anche `area/` + `src/tables.c` di basedmud
(`E2E_BASEDMUD`, default il checkout fratello `../basedmud`, solo in lettura), e configura i mondi con `WEBEDITOR_WORLDS`:
`pachimud` (default), `basedmud`, `basedmud-ro` (stessa copia, sola lettura), e, **solo se `E2E_DIKUMOD` e' impostata** su una cartella `lib/` esistente di dati Diku Modificato (nessun default; sola lettura sull'originale, i test lavorano su copie), `dikumod` (copia in sola lettura) e `dikumod-rw` (seconda copia scrivibile). Il prefisso dei file dati (`<prefisso>.wld`, ...) e' `dikumoddata`, o `E2E_DIKUMOD_PREFIX` se impostata. Senza `E2E_DIKUMOD` quei due mondi non esistono e `e2e/tests/dikumod.test.ts` viene saltato. Il `pachimud.db` reale non viene mai aperto. Se la porta e' occupata il setup si interrompe.

Variabili: `E2E_PORT` (8124), `E2E_CDP_URL`, `E2E_USER` / `E2E_PASSWORD` (default: utente di test creato dal
setup), `E2E_BASE_URL` / `E2E_SKIP_STACK`.

## Copertura

`tests/auth.test.ts` login (errore e successo), logout, redirect, dashboard con le 5 schede, fallback SPA.
`tests/zones.test.ts` lista, crea, vnum duplicato, range incoerente, modifica, clona, delete 409 su zona non vuota,
delete, editor reset (aggiungi/salva/ricarica/svuota). `tests/rooms.test.ts` crea con flag + uscita + extra
description, riapertura, modifica, clone, delete 409 (in uso da reset), mappa (nodi/archi/click), delete.
`tests/mobs.test.ts` e `tests/objects.test.ts` CRUD con chip dei flag creati con Invio e persistiti, errore
tradotto sul vnum duplicato, delete 409. `tests/pages.test.ts` nessuna chiave i18n grezza su tutte le pagine.
`tests/worlds.test.ts` selettore di mondo con basedmud (copia temporanea di `area/`, mondo scrivibile + mondo `basedmud-ro`
in sola lettura): capability nascoste, route guard, zone (anche id negativo), mob con `extra`, deep-link, sola lettura.
`tests/world.test.ts` panoramica/ricerca/grafo, `tests/players.test.ts` account e personaggi (seminati da
`support/seed_players.py`), `tests/instances.test.ts`, `tests/transfer.test.ts` (export + import in anteprima),
`tests/content.test.ts` (razze/classi su una copia di `definitions/`).
Ogni file verifica anche l'assenza di errori di console (i 401/409 attesi dei test negativi sono ammessi
esplicitamente con `session.allow`).

`tests/convert.test.ts` conversione BasedMud -> pachimud dalla pagina Conversione: arrivo in sola lettura non scegliibile, anteprima senza scritture, esecuzione con conferma e zona visibile nel mondo di arrivo.
