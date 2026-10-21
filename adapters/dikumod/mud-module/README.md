# livectl: modulo C per Diku Modificato (DikuMod1)

Canale di controllo live (protocollo `livectl` v1) tra l'editor, o un altro client, e il MUD in esecuzione. Specifica:
`docs/backend/live-control-protocol.md` (protocollo) e `docs/adapters/dikumod-live.md` (profilo e punti di innesto nel sorgente C).

| File | Contenuto |
|---|---|
| `livectl.c`, `livectl.h` | socket Unix, framing, token, limiti, audit, i 10 comandi (`ping info who player.get player.set zone.list zone.reset load.mob load.obj echo`) |
| `livectl_json.c`, `livectl_json.h` | parser/serializzatore JSON a limiti fissi, senza `malloc`, senza dipendenze dal gioco |
| `dikumod1-livectl.patch` | gli unici cambi ai file del gioco: `comm.c` (12 righe) e `Makefile` (2 righe) |
| `fuzz/fuzz_json.c` | fuzz semplice del parser (ASan + UBSan) |

Sorgente di riferimento: **DikuMod1** (`/dati/luca/muds/oldlinux/DikuMod1/src`, identico a `oldlinux.save/leu/src`). Altre varianti non sono considerate.

## Applicare

Non modificare mai i sorgenti originali: lavora su una copia.

```bash
M=/percorso/pachimudeditor/adapters/dikumod/mud-module
mkdir /tmp/mud && cp -r /percorso/DikuMod1/src /tmp/mud/src && cd /tmp/mud
patch -p1 < $M/dikumod1-livectl.patch
cp $M/livectl*.[ch] src/ && cd src
make depend && make leu LIVECTL_FLAGS=-DLIVECTL
```

Il patch aggiunge: `#include "livectl.h"` (con `#ifdef LIVECTL`), `livectl_init();` in `run_the_game` dopo `boot_db();`, `livectl_poll();` in coda a ogni
iterazione di `game_loop` (dopo `tics++;`), `$(LIVECTL_FLAGS)` in `MYFLAGS` e `livectl.o livectl_json.o` in `OBJS`. Senza `-DLIVECTL` il modulo
si riduce a tre funzioni vuote e il gioco si comporta come prima. Il codice compila come C++ `gnu++98`, come il resto del gioco.

### Cartella ufficiale `/dati/luca/muds/leu`

Qui il `Makefile` e' nella radice (non in `src/`) e usa un'altra forma di `OBJS`, quindi `dikumod1-livectl.patch` non si applica al Makefile
(hunk respinti). Usa `leu-livectl.patch` (`git apply` dalla radice di `leu`: `Makefile` e `src/comm.c`), poi `cp livectl*.[ch] src/` e
`make LIVECTL_FLAGS=-DLIVECTL`.

## Configurare (variabili d'ambiente del processo del MUD)

| Variabile | Default | Significato |
|---|---|---|
| `LIVECTL_SOCKET` | (nessuno: canale spento) | percorso **assoluto** del socket Unix, al massimo 107 caratteri; creato `0600` |
| `LIVECTL_TOKEN` | (obbligatorio) | segreto di 32..200 caratteri ASCII visibili; **cancellato dall'ambiente** dopo la lettura. Senza, il canale non parte |
| `LIVECTL_CLASSES` | `read` | `read,write` abilita `player.set zone.reset load.mob load.obj echo` |
| `LIVECTL_MAX_CONN` | `4` | connessioni massime (1..8) |
| `LIVECTL_AUDIT` | `livectl.audit` | file di audit append-only (relativo a `lib/` o assoluto); senza audit le scritture sono sospese |
| `LIVECTL_DENY_OBJ` | `150-199,1600,5311,13702,21113,21117,21120-21122` | vnum che `load.obj` non crea (la deny-list di `do_oload`) |
| `LIVECTL_ALLOW_UID` | solo l'UID del MUD | un UID in piu' ammesso a connettersi |

Interruttore di emergenza: un file `livectl.disable` nella cartella dati (`lib/`) impedisce l'attivazione all'avvio.
Il token non va nel yaml dell'editor (li' c'e' solo il nome della variabile, `token_env`) ne' negli script di avvio stampati nei log.

## Provare

```bash
# fuzz del parser (solo g++)
g++ -std=gnu++98 -O1 -g -fsanitize=address,undefined -I. fuzz/fuzz_json.c livectl_json.c -o /tmp/fuzz_json && /tmp/fuzz_json 500000 1

# suite di conformita' contro il gioco reale (copie temporanee in /tmp; richiede g++, make, patch)
DIKUMOD_SRC=/percorso/DikuMod1/src DIKUMOD_LIB=/percorso/DikuMod1/lib uv run pytest tests/live
# oppure contro un MUD gia' acceso (classi read,write, giocatore Tester in gioco)
LIVECTL_TEST_SOCKET=/tmp/mud/l.sock LIVECTL_TEST_TOKEN=... uv run pytest tests/live
```

Senza queste variabili `tests/live` prova solo il finto server Python (`tests/support/live_fake_server.py`).
