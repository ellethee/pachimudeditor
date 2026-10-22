# Canale di controllo live (protocollo `livectl`)

**Stato: protocollo v1 specificato; implementati il modulo C di riferimento per Diku Modificato (DikuMod1, `adapters/dikumod/mud-module/`), un finto server Python, la suite di conformita' (`tests/live/`) e, lato editor (SDK 1.5), il client, `LiveAdapter`, le rotte [`/api/world/live`](contract-live.md) e la pagina Giocatori. i comandi CLI `pachimudeditor live` (client sottile). Non implementato: componente per pachimud.** Descrive un canale tra l'editor (o un altro client) e un MUD **in esecuzione**: il client chiede informazioni
(chi e' connesso, stato del server) e fa modifiche immediate (giocatori connessi, reset di zona, creazione di mob/oggetti,
messaggi) senza fermare il gioco e senza toccare i file. Il caso di riferimento e' Diku Modificato ([profilo dikumod](../adapters/dikumod-live.md));
per pachimud (Python) e' **previsto** lo stesso protocollo servito da un componente `asyncio` nello stesso processo, come passo successivo a dikumod.

Il protocollo e' **indipendente dall'editor**: qualunque client in possesso del token e dell'accesso al socket puo' usarlo. L'editor e' il client di riferimento (autentica gli utenti e applica i permessi); la [riga di comando](#client-da-riga-di-comando) e' un client sottile per gli script.

Il canale **affianca** la modifica su file dei giocatori ([contratto giocatori su file](contract-players-files.md)), non la sostituisce:
i giocatori **non connessi** restano sui file, quelli connessi passano dal canale.

Parole normative: **DEVE**, **NON DEVE**, **DOVREBBE**, **PUO'** hanno il significato di RFC 2119.

## Scopo e non-scopi

Scopo:

- osservare un MUD acceso (`ping`, `info`, `who`, `player.get`, `zone.list`);
- modificare lo **stato in memoria** di un giocatore connesso e, a scelta, salvarlo con il meccanismo del gioco (`player.set`);
- azioni di servizio: forzare il reset di una zona, creare un mob o un oggetto, mandare un messaggio.

Non-scopi della versione 1:

- niente esecuzione di comandi arbitrari del gioco (`exec`, `force`): **mai**, e il nome e' riservato;
- niente arresto/riavvio/copyover dal canale: classe `danger`, [disattivata di default](#classi-di-comandi) e non definita in v1;
- niente editing del mondo (stanze, mob, oggetti, zone): resta sui file e richiede il gioco fermo
  ([adapter dikumod](../adapters/dikumod.md));
- niente notifiche push dal MUD all'editor (il protocollo le prevede come estensione, vedi [compatibilita'](#compatibilita-e-versioni)).

## Modello di minaccia

Il canale e' una **porta di amministrazione** dentro il processo del gioco: un errore di sicurezza o di robustezza qui vale piu' di
un errore nell'editor. Ipotesi:

| Attore | Fiducia | Note |
|---|---|---|
| Il processo del MUD | si' | esegue il modulo; un bug del modulo e' un bug del gioco (puo' farlo cadere) |
| Il client autenticato dal token (editor, CLI, script) | si' | l'editor autentica i propri utenti e applica i permessi; il MUD conosce solo il token e non distingue i client |
| Altri processi dello stesso utente Unix | **no** | il token e' la seconda difesa dopo i permessi del socket |
| Altri utenti della macchina | no | non devono poter nemmeno aprire il socket |
| Rete | no | nessun ascolto fuori da loopback; il protocollo non e' pensato per Internet |
| Un giocatore del MUD | no | non puo' raggiungere il canale; i **testi** dei giocatori restano dati, mai comandi |

Minacce considerate e contromisure (dettaglio nella [sicurezza](#sicurezza)):

1. **Accesso non autorizzato al canale**: permessi del socket (`0600`), controllo `SO_PEERCRED` sull'UID, token segreto, solo loopback per TCP.
2. **Input malformato o ostile** (client compromesso o bug dell'editor): parser rigoroso con limiti fissi, nessuna allocazione
   proporzionale all'input, fail-closed (errore + chiusura), nessun comando fuori dalla allowlist.
3. **Abuso di un client valido** (editor compromesso): classi di comandi, allowlist, limiti di frequenza, validazione dei valori
   come per i file, **audit** lato MUD indipendente da quello dell'editor. Un editor compromesso resta un rischio: il canale ne limita
   il danno ma non lo annulla (vedi [rischi aperti](#rischi-aperti-e-decisioni)).
4. **Denial of service** (client lento, connessioni a raffica, richieste a raffica): connessioni massime, buffer limitati,
   budget di tempo per iterazione del ciclo di gioco, chiusura dei client che non leggono; nessuna attesa bloccante nel thread del gioco.
5. **Perdita di segreti**: il token non compare mai nel yaml dell'editor, nei log, nei messaggi d'errore, negli esempi delle API.
6. **Iniezione tramite testo**: i testi inviati al MUD (`echo`, nomi) sono neutralizzati secondo il profilo (codici colore e
   formattazione del gioco, caratteri di controllo, codifica).

## Trasporto e framing

**Socket Unix** `SOCK_STREAM` (default). Il percorso e' **assoluto** e configurato nel MUD (il gioco fa `chdir` nella cartella
dati: un percorso relativo cambierebbe significato). Regole per il MUD:

- crea il socket con `umask(0177)` (file `0600`) in una cartella non scrivibile da altri; se il file esiste, tenta `connect()`: se
  qualcuno risponde, **non parte** (due istanze), altrimenti lo rimuove e lo ricrea (socket rimasto dopo un crash);
- rimuove il file alla chiusura ordinata;
- apre i descrittori con `O_NONBLOCK` e `FD_CLOEXEC` (il gioco puo' fare `system()`: i figli non devono ereditare il canale);
- usa `SO_PEERCRED` per verificare che l'UID del client sia nell'elenco ammesso (default: lo stesso UID del MUD) e lo scrive nell'audit.

**TCP opzionale** su `127.0.0.1` soltanto (`bind` a un altro indirizzo e' un errore di configurazione, il modulo non parte). E' pensato
per ambienti dove il socket Unix non e' condivisibile (container, WSL). Il token e' obbligatorio come per Unix. Niente TLS: il
canale e' locale; fuori da loopback **NON DEVE** essere esposto (se serve, tunnel SSH).

**Framing**: una richiesta o risposta per riga, JSON UTF-8 terminato da `\n` (accettato anche `\r\n`). Regole:

- lunghezza massima di una riga di richiesta: `max_line` (default 4096 byte, massimo configurabile 16384). Una riga piu' lunga produce
  `line_too_long` e la **chiusura** della connessione (non si puo' risincronizzare in modo sicuro);
- il JSON e' un solo oggetto per riga, senza `\n` interni; byte non UTF-8 o NUL: `bad_json`;
- profondita' massima 5 (un `obj.set` con `affects` arriva a `params.set.affects[i]`), al massimo 32 chiavi per oggetto, stringhe fino a 512 byte, array fino a 32 elementi;
- **numeri solo interi** (nessun `1.5`, nessun esponente): servono ai campi dei MUD e evitano ambiguita' di arrotondamento;
- chiavi duplicate nello stesso oggetto: `bad_json`; chiavi sconosciute in `params`: `bad_params` (strict, vedi [compatibilita'](#compatibilita-e-versioni));
- le risposte possono superare `max_line` fino a `max_response` (default 65536 byte); se una risposta non ci sta, il comando
  (es. `who`) usa il parametro `limit` e restituisce `truncated: true`.

Le richieste di una connessione sono eseguite **in ordine** e ognuna riceve esattamente una risposta con lo stesso `id`. L'editor PUO'
tenere piu' richieste in volo (fino a `max_pending`, default 8).

## Handshake, versioni e capability

La prima richiesta di ogni connessione DEVE essere `hello`; fino al `hello` riuscito ogni altro comando risponde `auth_required`.
Il server **non** manda nulla alla connessione finche' il client non scrive (nessun banner: meno informazioni a chi non e' autenticato).
Entro `hello_timeout` (default 5 s) il `hello` deve arrivare, altrimenti la connessione e' chiusa.

Richiesta:

```json
{"id": 1, "cmd": "hello", "params": {
  "protocols": [1],
  "token": "<segreto condiviso>",
  "client": "pachimudeditor/0.2.0",
  "actor": "mario.rossi"
}}
```

- `protocols`: versioni intere che il client sa parlare; il server sceglie la **piu' alta in comune**, altrimenti
  `protocol_unsupported` con `params.supported`.
- `token`: vedi [token](#token). Mai ripetuto dopo l'handshake.
- `client`: stringa informativa (max 64). `actor`: utente dell'editor che ha causato la sessione (max 64), **dichiarato**
  dall'editor e non verificabile dal MUD; finisce nell'audit come informazione, non come prova d'identita'.

Risposta di successo:

```json
{"id": 1, "ok": true, "result": {
  "protocol": 1,
  "mud": {"kind": "dikumod", "name": "LeU", "version": "1.7.0 cdrom", "module": "livectl 0.1"},
  "limits": {"max_line": 4096, "max_response": 65536, "max_pending": 8, "request_timeout_ms": 2000, "max_text": 400},
  "features": ["inventory"],
  "commands": {
    "ping":       {"class": "read"},
    "info":       {"class": "read"},
    "who":        {"class": "read"},
    "player.get": {"class": "read",  "fields": ["gold", "bankGold", "exp", "hit", "mana", "move", "str"]},
    "player.set": {"class": "write", "fields": ["gold", "bankGold", "exp", "hit", "mana", "move", "str"]},
    "zone.list":  {"class": "read"},
    "zone.reset": {"class": "write"},
    "load.mob":   {"class": "write"},
    "load.obj":   {"class": "write"},
    "echo":       {"class": "write"},
    "player.inventory": {"class": "read"},
    "obj.get":    {"class": "read"},
    "obj.set":    {"class": "write"},
    "obj.remove": {"class": "write"}
  }
}}
```

**Capability discovery**: l'editor costruisce l'interfaccia da `commands` e `fields` e non da una versione del MUD. Un comando assente
da `commands` (non implementato, classe disattivata o fuori allowlist) NON DEVE essere inviato; se lo e' risponde `unknown_command` o
`command_disabled`. `features` e' un elenco di stringhe per estensioni opzionali dello stesso protocollo (es. `idempotency_key`; `inventory` = i comandi [`player.inventory`, `obj.get`, `obj.set`, `obj.remove`](#riferimenti-agli-oggetti)). Una feature dichiarata implica che i suoi comandi siano presenti in `commands` (la classe `write` resta quella configurata: con le scritture spente compaiono solo `player.inventory` e `obj.get`).

Dopo 3 `hello` falliti sulla stessa connessione, o `hello_timeout`, la connessione viene chiusa. Una connessione autenticata resta
aperta; se resta senza richieste per `idle_timeout` (default 300 s) il server la chiude e il client riconnette (e rifa' `hello`).

## Formato di richieste, risposte ed errori

Richiesta:

```json
{"id": 7, "cmd": "player.get", "params": {"name": "Mario"}}
```

- `id`: intero 0..2^53-1 oppure stringa ASCII di al massimo 64 caratteri; obbligatorio; ripetuto nella risposta. Il server NON
  controlla l'unicita'.
- `cmd`: nome del comando, `[a-z]+(\.[a-z]+)*`, max 32 caratteri.
- `params`: oggetto, facoltativo se il comando non ha parametri.

Risposta di successo e di errore:

```json
{"id": 7, "ok": true,  "result": {"name": "Mario", "state": "playing", "fields": {"gold": 1500}}}
{"id": 7, "ok": false, "error": {"code": "not_found", "message": "giocatore non connesso", "params": {"what": "player"}}}
```

Un errore su una riga che non si riesce a interpretare (`bad_json`, `line_too_long`) ha `"id": null`.

`error.code` e' **stabile** (l'editor ci costruisce sopra la logica e le traduzioni); `error.message` e' testo libero per i log
(non stabile, mai contiene segreti ne' dati dei giocatori oltre al nome). `error.params` e' facoltativo.

| `code` | Quando | Ritentabile |
|---|---|---|
| `bad_json` | riga non JSON valido, byte non UTF-8, chiave duplicata, numero non intero, limiti di profondita'/chiavi/stringhe | no |
| `line_too_long` | riga oltre `max_line` (la connessione si chiude) | no |
| `bad_request` | manca `id` o `cmd`, tipi sbagliati, `cmd` malformato | no |
| `auth_required` | comando prima del `hello` | no |
| `auth_failed` | token errato o mancante (nessun dettaglio su quale dei due) | no |
| `protocol_unsupported` | nessuna versione in comune (`params.supported`) | no |
| `unknown_command` | comando non definito da questo MUD | no |
| `command_disabled` | comando noto ma fuori dalla allowlist o di una classe disattivata | no |
| `bad_params` | parametro mancante, di tipo sbagliato o sconosciuto | no |
| `value_out_of_range` | valore fuori dall'intervallo (`params.field`, `params.min`, `params.max`) | no |
| `unencodable_text` | testo non rappresentabile nella codifica del MUD (es. emoji in latin-1) | no |
| `not_found` | giocatore, zona, vnum o stanza inesistente (`params.what`) | no |
| `stale_ref` | il riferimento a un oggetto non punta piu' all'oggetto letto (vnum o impronta diversi, oggetto spostato o sparito): nessuna modifica ([riferimenti](#riferimenti-agli-oggetti)) | si', dopo aver riletto l'inventario |
| `player_not_playing` | il giocatore esiste ma non e' nello stato di gioco normale (login, menu, link morto) | si', piu' tardi |
| `player_busy` | il giocatore e' in uno stato che il comando non gestisce (trasformato, in editor di testo, switch di un immortale) | si', piu' tardi |
| `forbidden_by_policy` | regola del MUD (es. non creare immortali, vnum in deny-list) | no |
| `rate_limited` | superato il limite di richieste (`params.retry_after_ms`) | si' |
| `busy` | coda piena o budget di tempo dell'iterazione esaurito | si' |
| `too_many_connections` | connessioni massime raggiunte (la connessione si chiude subito) | si' |
| `unavailable` | il MUD sta spegnendosi | no |
| `internal` | errore interno del modulo; il MUD resta attivo e l'evento e' nell'audit | no |

Regole per gli errori: **fail-closed** (nel dubbio si rifiuta), un errore NON DEVE lasciare modifiche a meta' (i comandi con piu'
effetti validano tutto prima di applicare qualcosa), nessun errore fa terminare il processo del MUD.

## Esecuzione sul thread del gioco

Il server di gioco e' a thread singolo: il modulo non crea thread e non prende lock. Il canale viene servito in un punto fisso del
ciclo principale, **tra un'iterazione e l'altra**, quando nessun comando di giocatore, combattimento o azione di mob e' in corso e le
liste del gioco sono in stato coerente. Conseguenze:

- ogni comando del canale e' **atomico** rispetto al gioco: nessun giocatore agisce a meta' di un `player.set`;
- il poll e' **non bloccante** (`poll()` con timeout 0, `accept`/`recv`/`send` non bloccanti): non si aspetta mai un client;
- ogni iterazione ha un **budget**: al massimo `max_per_tick` richieste (default 16) e `tick_budget_us` (default 5000) di tempo;
  il resto resta in coda per l'iterazione successiva; oltre `max_pending` per connessione la richiesta riceve `busy`;
- la **latenza minima** e' quella del ciclo del gioco (per Diku Modificato un'iterazione ogni 250 ms, vedi [profilo](../adapters/dikumod-live.md));
  `request_timeout_ms` (lato editor, default 3000 ms) deve essere maggiore di alcune iterazioni;
- i comandi NON DEVONO eseguire I/O bloccante (file, DNS, `system`); l'unica eccezione e' il salvataggio di un giocatore
  (`player.set` con `save`), che e' la stessa operazione che il gioco fa per ogni giocatore che digita `save`;
- le risposte sono scritte non bloccando: quello che non entra nel buffer del socket resta in coda (limite `max_response` per
  connessione); se la coda supera il limite perche' il client non legge, la connessione e' chiusa.

**Sotto carico**: se il gioco e' lento (iterazioni lunghe) il canale rallenta con lui; l'editor vede timeout. Un timeout NON e' un
fallimento: il comando puo' essere stato eseguito. Per questo:

- i comandi di lettura sono **idempotenti** e ritentabili senza condizioni;
- `player.set` e' idempotente a parita' di valori (impostare gli stessi valori due volte produce lo stesso stato), ma la risposta
  perduta nasconde il vecchio valore: dopo un timeout l'editor DEVE rileggere con `player.get` prima di ritentare;
- `zone.reset`, `load.mob`, `load.obj` ed `echo` **non sono idempotenti**: l'editor NON DEVE ritentarli in automatico dopo un timeout;
  mostra «esito sconosciuto». Se il MUD dichiara la feature `idempotency_key`, il client puo' aggiungere `params.key` (stringa fino
  a 64) e il server ricorda per 60 s le ultime 128 chiavi con la risposta: lo stesso `key` restituisce la risposta memorizzata senza
  rieseguire (anche dopo una riconnessione).

## Sicurezza

### Token

- Segreto condiviso casuale di almeno **32 byte** (64 caratteri esadecimali). Si genera con `openssl rand -hex 32` o simili.
- Lato MUD: letto all'avvio dalla variabile d'ambiente `LIVECTL_TOKEN` (decisione presa: niente file del token). Nota: l'ambiente di un
  processo e' leggibile dallo stesso utente in `/proc/<pid>/environ` e spesso compare negli script di avvio; il modulo quindi **cancella**
  la variabile dall'ambiente dopo averla letta (`unsetenv`) e lo script di avvio NON DEVE stamparla. Se il token manca o e' piu' corto di
  32 caratteri il modulo **non si attiva** e lo scrive nel log del gioco (il gioco parte comunque, senza canale).
- Lato editor: il yaml del mondo contiene solo il **nome** della variabile (`token_env`), il valore sta nel `.env` della cartella
  di lavoro (regola gia' valida per i segreti: [configurazione](../guide/configuration.md)). Il token NON DEVE comparire nel yaml, nei log, nelle
  eccezioni, nelle risposte API, nei campi `error`, nell'audit, nella cronologia dei comandi.
- Il confronto avviene a **tempo costante** (nessuna uscita anticipata al primo byte diverso, anche con lunghezze diverse).
- Rotazione: cambiare il token nell'ambiente del MUD (richiede il riavvio del gioco) e nel `.env` dell'editor; le connessioni gia' autenticate restano valide fino alla chiusura.
- Protezione dai tentativi: dopo 3 `hello` falliti la connessione e' chiusa; piu' di 10 fallimenti in 60 s fanno rispondere
  `rate_limited` ai `hello` per 30 s **senza nemmeno confrontare** il token. Il modulo non dorme mai nel thread del gioco.
- Evoluzione: `hello` e' stato pensato per ammettere un secondo metodo (sfida con HMAC, cosi' il segreto non passa nel canale);
  la versione 1 usa il token in chiaro perche' il canale e' Unix/loopback e perche' evita un'implementazione crittografica dentro il gioco.

### Classi di comandi

| Classe | Comandi v1 | Stato di default |
|---|---|---|
| `read` | `ping`, `info`, `who`, `player.get`, `zone.list` | attiva |
| `write` | `player.set`, `zone.reset`, `load.mob`, `load.obj`, `echo` | attiva solo se abilitata nella configurazione del MUD (default: **disattivata**; il canale nasce in sola lettura) |
| `danger` | riservati: `server.shutdown`, `server.reboot`, `player.kick`; `exec` e' escluso per sempre | disattivata, **non definita in v1** |

La allowlist e' una tabella costante nel modulo (nome, classe, funzione); non esiste nessun meccanismo per aggiungere comandi a runtime
ne' per chiamare funzioni per nome. La configurazione puo' solo **togliere** comandi o classi. `commands` in `hello` elenca solo cio' che e' attivo.

### Limiti (tutti configurabili, con questi default)

| Limite | Default | Effetto al superamento |
|---|---|---|
| `max_line` | 4096 byte | `line_too_long` + chiusura |
| `max_response` | 65536 byte | risposta troncata dal comando (`truncated`) o connessione chiusa se il client non legge |
| `max_connections` | 4 | `too_many_connections` e chiusura |
| `max_pending` per connessione | 8 | `busy` |
| richieste al secondo | 20 per connessione, 50 totali (token bucket) | `rate_limited` con `retry_after_ms` |
| `max_per_tick`, `tick_budget_us` | 16, 5000 | il resto aspetta l'iterazione successiva |
| `hello_timeout`, `idle_timeout` | 5 s, 300 s | chiusura |
| `max_text` | 400 byte (dopo conversione) | `bad_params` |
| `who` | al massimo 200 voci | `truncated: true` |
| `player.inventory` | `limit` 1..200 oggetti (default 100), e comunque entro `max_response` | `truncated: true` |
| testi di un oggetto | `name` 127, `short_description` 127, `description` 255 byte (latin-1) | `bad_params` |

Il modulo NON DEVE fare allocazioni la cui dimensione dipende dall'input oltre questi limiti: buffer di riga e di risposta sono
array di dimensione fissa per connessione, il parser lavora in-place senza `malloc` proporzionale al testo.

### Validazione e testi

I valori dei campi giocatore sono validati con **le stesse regole** della modifica su file
(tipo e intervallo del campo del formato, vedi [formato dikumod](../formats/dikumod.md#9-file-giocatore-e-rent)): un valore valido
per il file lo e' per il canale e viceversa. I nomi dei campi sono quelli del DTO dei giocatori (`gold`, `bankGold`, `exp`, ...).

I testi che entrano nel gioco (`echo`, eventuali notifiche): niente caratteri di controllo (neppure `\n`: il modulo aggiunge i terminatori
di riga del gioco), conversione dalla codifica del canale (UTF-8) a quella del MUD (per Diku Modificato `latin-1`, errore
`unencodable_text` se non rappresentabile), e **neutralizzazione** dei codici di formattazione del MUD secondo il profilo (nel profilo dikumod
il `$`). I nomi di giocatore si accettano solo con la regola dei file (`[A-Za-z][A-Za-z0-9_-]{0,19}`).

### Audit

Il modulo scrive un registro **append-only** proprio (default `livectl.audit` nella cartella dati del MUD), una riga per richiesta
a partire dal `hello`:

```
2026-10-21T14:03:11+0200 conn=3 uid=1000 pid=4242 actor=mario.rossi cmd=player.set target=Mario result=ok fields=gold,exp saved=1
2026-10-21T14:03:40+0200 conn=3 uid=1000 pid=4242 actor=mario.rossi cmd=load.obj target=room:3001 vnum=3012 result=error code=not_found
```

Per gli oggetti la riga porta il comando, il giocatore, il `ref` e i **nomi** dei campi cambiati (per i campi numerici anche `vecchio>nuovo`; per i testi mai il contenuto):

```
2026-10-21T16:48:07+0200 conn=8 uid=1000 pid=4242 actor=mario.rossi cmd=obj.set target=Tester result=ok ref=inv:0 values.1:8>5 extra_flags:0>3 name saved=1
2026-10-21T16:48:09+0200 conn=8 uid=1000 pid=4242 actor=mario.rossi cmd=obj.remove target=Tester result=ok ref=eq:5 vnum=9 items=1 saved=1
```

Contenuto: data, connessione, UID/PID del peer, `actor` dichiarato, comando, bersaglio, esito o `code`, e per le scritture i **nomi** dei campi (e
`vecchio->nuovo` dei valori numerici). Mai: token, password, hash, testi liberi interi (`echo` si registra troncato a 80 byte), contenuto di file.
Una riga sintetica per le scritture va anche nel log normale del gioco con formato fisso (`"%s"` e argomenti, mai testo del client
come stringa di formato). Se l'audit non si puo' scrivere (disco pieno, permessi) i comandi della classe `write` rispondono `unavailable`: **senza traccia non si
modifica**; la lettura continua.

## Comandi

Nei comandi, `name` e' il nome del personaggio (confronto senza maiuscole/minuscole, risposta con la forma canonica). Salvo diversa
indicazione tutti i campi elencati in `params` sono obbligatori e nessun altro e' ammesso.

### `ping`

Classe `read`. Parametri: nessuno. Risposta `{"pong": true, "time": 1792590191}` (`time` = secondi Unix del server).
Effetti collaterali: nessuno. Idempotente.

### `info`

Classe `read`. Parametri: nessuno. Risposta:

```json
{"mud": {"kind": "dikumod", "name": "LeU", "version": "1.7.0 cdrom"},
 "started_at": 1792500000, "now": 1792590191, "uptime_s": 90191,
 "pulse": 1432, "ticks": 8123456, "lag_us": 1200,
 "players": {"playing": 12, "linkdead": 1, "connecting": 2},
 "world": {"zones": 90, "mob_protos": 1480, "obj_protos": 2630}}
```

`pulse` e' il contatore del ciclo come lo tiene il gioco (puo' ripartire da zero); `ticks` e' un contatore monotono tenuto dal modulo.
`lag_us` e' facoltativo (se il MUD misura la latenza dell'iterazione). Effetti collaterali: nessuno. Idempotente.

### `who`

Classe `read`. Parametri facoltativi: `prefix` (stringa, solo i nomi che iniziano cosi'), `limit` (1..200, default 100),
`linkdead` (bool, default `true`: include i giocatori col collegamento caduto ma ancora nel mondo). Risposta:

```json
{"players": [
  {"name": "Mario", "state": "playing", "level": 34, "levels": {"warrior": 34, "thief": 12},
   "race": 3, "sex": 1, "room": 3001, "zone": 13, "position": 8,
   "fighting": false, "idle": 12, "immortal": false, "invisible": 0}
 ],
 "count": 1, "truncated": false}
```

`state`: `playing`, `linkdead`, `polymorph` (il personaggio e' trasformato: `name` e' quello reale). Non compaiono i collegamenti
ancora in login. L'indirizzo di rete NON e' mai nella risposta (dato personale). `levels` ha per chiavi i nomi di classe del formato (`magic_user`, `cleric`, `warrior`, `thief`, `druid`, `monk`, `barbarian`, `sorcerer`, `paladin`, `ranger`, `psi`); `race`, `sex` e `position` sono i **valori numerici** del MUD (le tabelle di nomi sono nelle `enums` dell'adapter), `idle` e' il contatore di inattivita' del gioco nelle sue unita'.
Effetti collaterali: nessuno. Idempotente. Ordine: lista del gioco (non garantito stabile).

### `player.get`

Classe `read`. Parametri: `name`. Risposta: `{"name", "state", "fields": {...}}` con i campi dichiarati in `hello` (`commands["player.get"].fields`),
**valori correnti in memoria** (possono differire dal file finche' non c'e' un salvataggio). Errori: `not_found` (nessun
giocatore con quel nome nel mondo), `player_not_playing`. Effetti collaterali: nessuno. Idempotente.

### `player.set`

Classe `write`. Parametri: `name`, `set` (oggetto campo -> valore, da 1 a 16 campi), `save` (bool facoltativo, default `true`), `confirm_immortal` (bool facoltativo, default `false`). Risposta (le chiavi di `applied` sono i nomi dei campi, con il punto per quelli annidati: `conditions.drunk`, `levels.warrior`):

```json
{"name": "Mario",
 "applied": {"gold": {"old": 1500, "new": 99999}, "exp": {"old": 80000, "new": 120000}},
 "saved": true, "warnings": []}
```

Semantica:

1. il giocatore deve essere in stato `playing` e senza condizioni particolari (non trasformato, non in un editor di testo): altrimenti
   `player_not_playing` / `player_busy`;
2. **tutti** i campi sono validati (nome del campo nella lista `fields`, tipo, intervallo, regole di policy) **prima** di applicare
   qualunque modifica; un solo campo non valido annulla l'intera richiesta (`bad_params`, `value_out_of_range`, `forbidden_by_policy`);
3. le modifiche sono applicate in memoria e il MUD ricalcola gli effetti derivati come fa per le proprie azioni (profilo);
4. con `save: true` il giocatore e' salvato con la stessa procedura del comando `save` del gioco; `saved` dice se e' riuscito (se
   no, la modifica resta in memoria e c'e' un `warnings` con il codice del salvataggio fallito: l'editor lo mostra, non ritenta).

**Livelli e immortali (avvertenza e sblocco).** `levels` e' modificabile (oggetto classe -> livello). **Promuovere** una classe a un livello di **51 o piu'** (`LOW_IMMORTAL`; cioe' nuovo livello >= 51 e maggiore di quello attuale)
crea o promuove un immortale: il gioco stesso lo vieta ai non implementatori. Il canale non lo impedisce in modo assoluto ma lo tratta come
operazione pericolosa: senza `confirm_immortal: true` la richiesta intera e' rifiutata con `forbidden_by_policy` (`params.reason = "immortal_level"`, `params.level`);
con `confirm_immortal: true` e' eseguita, la risposta ha `"warnings": ["immortal_level"]` e l'audit riporta la conferma. L'editor DEVE mostrare
un'avvertenza esplicita («stai creando un immortale: avra' i poteri di un dio nel gioco») e inviare il flag solo dopo la conferma dell'utente.
Mantenere o abbassare un livello gia' da immortale non richiede conferma. Si possono impostare solo classi che il giocatore ha gia' (livello > 0), altrimenti `forbidden_by_policy` (`params.reason = "class_not_owned"`); il massimo assoluto e' 59.

Effetti collaterali: il giocatore puo' ricevere messaggi del gioco; il file del giocatore cambia solo con `save`. Idempotente a parita' di
valori (vedi [esecuzione](#esecuzione-sul-thread-del-gioco)). Solo giocatori **connessi**: per un giocatore non connesso la modifica
resta sui file ([giocatori su file](contract-players-files.md)).

### `zone.list`

Classe `read`. Parametri: nessuno. Risposta: elenco delle zone **come le vede il gioco** (`index`, `num` del file, `name`, `top`,
`lifespan` in minuti, `age`, `reset_mode`, `started`). Serve a tradurre una zona dell'editor nell'indice usato dal gioco: i due
possono non coincidere (vedi [limiti noti dell'adapter](../adapters/dikumod.md#limiti-noti)). Aggiunto rispetto alle decisioni di partenza proprio per
questo. Effetti collaterali: nessuno. Idempotente.

### `zone.reset`

Classe `write`. Parametri: **uno solo** tra `zone` (indice di `zone.list`) e `room` (vnum di una stanza: la zona e' quella della stanza),
`only_if_empty` (bool facoltativo, default `false`: non esegue se un giocatore e' nella zona e risponde `result.executed=false`).
Risposta `{"zone": 4, "name": "Midgaard", "executed": true}`.

Semantica: esegue i comandi di reset della zona **con le regole normali del gioco** (limiti `max` per mob/oggetto, controllo dei
combattimenti nella stanza). Un reset **aggiunge** quello che manca: non elimina mob e oggetti gia' presenti. Azzera l'eta' della zona. Se la zona
era gia' in coda per il reset automatico, la voce in coda e' rimossa (niente doppio reset). Errori: `not_found`, `forbidden_by_policy`
(zone non resettabili dal canale: profilo). Non idempotente in senso stretto (puo' creare altri mob se nel frattempo ne sono stati
uccisi), ma ripetere subito dopo non cambia lo stato.

### `load.mob`

Classe `write`. Parametri: `vnum` (intero), **uno solo** tra `room` (vnum di stanza) e `player` (nome: il mob appare nella stanza del giocatore),
`count` (1..10, default 1), `notify` (bool, default `false`: messaggio neutro ai presenti). Risposta:
`{"loaded": [{"vnum": 3001, "name": "...", "room": 3001}]}`. Il mob e' creato dal prototipo del mondo **senza** controllo del numero massimo di
istanze (a differenza del reset di zona). Errori: `not_found` (vnum, stanza o giocatore), `player_not_playing`, `value_out_of_range`
(`count`). Non idempotente.

### `load.obj`

Classe `write`. Parametri: `vnum`, **uno solo** tra `room` e `player` (l'oggetto va nell'inventario del giocatore), `count` (1..10, default 1),
`notify`. Risposta `{"loaded": [{"vnum": 3012, "name": "...", "where": "room:3001"}]}`. Il MUD puo' avere una **deny-list** di vnum non
creabili a mano (il gioco ne ha una per il comando degli immortali): vnum in lista -> `forbidden_by_policy`. La risposta ha sempre `warnings`: con destinazione `player` e `vnum` > 32767 contiene `"vnum_not_saveable"` (il rent del gioco salva il vnum come intero a 16 bit: al salvataggio l'oggetto si corrompe; l'editor DEVE mostrare l'avviso). Non idempotente.

### `echo`

Classe `write`. Parametri: `text` (1..`max_text` byte), `to` (oggetto con **una sola** chiave: `all` (`true`), `player` (nome), `room` (vnum)). Risposta
`{"recipients": 12}`. `all` raggiunge i giocatori in stato `playing`. Il testo e' neutralizzato come descritto in [validazione e testi](#validazione-e-testi). Non idempotente.

### Riferimenti agli oggetti

Feature `inventory`. Un oggetto del gioco e' una struttura in memoria che puo' sparire, essere spostata o ricreata fra due richieste (il giocatore raccoglie, posa,
indossa, muore, un reset di zona distrugge): un puntatore, o un indirizzo, tenuto dal client non e' mai valido. Il **`ref`** e' percio' un **percorso**, risolto dal MUD a ogni
richiesta, e nelle scritture e' accompagnato da un controllo `expect` obbligatorio.

- **`ref`**: stringa `eq:<slot>` per un oggetto indossato (`slot` = posizione di equipaggiamento del gioco) oppure `inv:<i>` per un oggetto portato (`i` = posizione nell'elenco
  dell'inventario, da 0), seguita da `/<j>` per ogni contenitore attraversato (`j` = posizione nel contenuto). Esempi: `eq:5`, `inv:2`, `inv:2/0` (primo oggetto nel terzo oggetto portato),
  `inv:2/0/1`. Al massimo 8 livelli; indici da 0 a 100000. Una stringa che non rispetta la grammatica e' `bad_params`.
- **`expect`**: oggetto `{"vnum": <intero|null>, "fp": "<8 cifre esadecimali>"}` con i valori letti dal client in `player.inventory`/`obj.get`. `vnum` e' il numero del prototipo (`null` per un
  oggetto creato dal gioco senza prototipo); `fp` e' l'**impronta**, un hash a 32 bit calcolato dal MUD su vnum, tipo, `name`, `short_description`, `description`, `extra_flags`, i quattro valori e
  gli affect; **non** include `weight` (cambia da solo per il contenuto di un contenitore) ne' `timer` (scala da solo). L'impronta e' opaca: il client la confronta e la rimanda, non la calcola.
- Se il `ref` non risolve a nessun oggetto o `expect` non coincide: **`stale_ref`**, senza modificare nulla. In `obj.get` `expect` e' facoltativo (senza `expect` un `ref` inesistente e' `not_found`).
- Gli indici si spostano: una bottiglia nuova in testa all'inventario fa scalare tutti gli `inv:i`. Un client DEVE rileggere (`player.inventory`) subito prima di scrivere, usare `ref` e `fp`
  dell'ultima lettura e, su `stale_ref`, rileggere e chiedere di nuovo all'utente: mai ritentare in automatico con un `ref` ricalcolato.

### `player.inventory`

Classe `read`, feature `inventory`. Parametri: `name`, `brief` (bool, default `false`: solo `ref`, `fp`, `vnum`, `slot`, `depth`, `name`, `short_description`, `type`, `contents`), `limit` (1..200, default 100). Risposta:

```json
{"name": "Tester", "carry_weight": 12, "carry_items": 2, "count": 4, "truncated": false,
 "items": [
  {"ref": "eq:5", "fp": "9f3c01aa", "vnum": 9, "slot": 5, "depth": 0, "name": "giubbotto pelle", "short_description": "Un giubbotto di pelle",
   "type": 9, "contents": 0, "description": "C'e' un giubbotto di pelle per terra", "values": [2, 2, 0, 0], "weight": 6, "extra_flags": 0, "timer": 0,
   "affects": [{"location": 0, "modifier": 0}, {"location": 0, "modifier": 0}, {"location": 0, "modifier": 0}, {"location": 0, "modifier": 0}, {"location": 0, "modifier": 0}]},
  {"ref": "inv:1", "fp": "01b2c3d4", "vnum": 14, "slot": null, "depth": 0, "name": "borsa piccola", "contents": 1, "...": "..."},
  {"ref": "inv:1/0", "fp": "a3ba504d", "vnum": 3001, "slot": null, "depth": 1, "name": "birra bottiglia", "contents": 0, "...": "..."}
 ]}
```

Elenco **piatto** di tutti gli oggetti del giocatore, prima quelli indossati (per `slot`), poi quelli portati; il contenuto di un contenitore segue il contenitore, con `depth` + 1 (in preordine). Le stesse
liste del gioco sono percorse con un limite: oltre 8 livelli o `limit` oggetti o `max_response` il resto e' omesso e `truncated` vale `true`. `carry_weight` e `carry_items` sono i contatori del gioco.
Il peso `weight` di un contenitore **comprende il contenuto**, come nel gioco. Solo giocatori `playing`; un link morto e' `player_not_playing`. Effetti collaterali: nessuno. Idempotente.

### `obj.get`

Classe `read`, feature `inventory`. Parametri: `name`, `ref`, `expect` (facoltativo). Risposta `{"name": ..., "item": {...}}` con tutti i campi di `player.inventory` e in piu' quelli di sola lettura
`wear_flags`, `cost`, `cost_per_day`, `bitvector`. Errori: `bad_params` (`ref`), `not_found`, `stale_ref`, `player_not_playing`. Idempotente.

### `obj.set`

Classe `write`, feature `inventory`. Parametri: `name`, `ref`, `expect` (**obbligatorio**), `set`, `save` (default `true`, come in [`player.set`](#playerset)). `set` e' una patch **parziale** (1-8 chiavi tra le seguenti, nessun'altra):

| Campo | Tipo e intervallo |
|---|---|
| `name` | parole chiave: 1..127 byte (latin-1) |
| `short_description` | 1..127 byte |
| `description` | la descrizione a terra: 1..255 byte |
| `values` | array di 1-4 elementi, ciascuno `null` (invariato) o intero a 32 bit con segno; la posizione e' l'indice del valore |
| `weight` | 0..32767 |
| `extra_flags` | 0..2147483647 |
| `timer` | 0..1000000, oppure -7000000 (nessun timer) |
| `affects` | array di 1-5 elementi, ciascuno `null` (invariato) o `{"location": 0..64, "modifier": -32768..32767}`; la posizione e' lo slot di affect; `{"location": 0, "modifier": 0}` svuota lo slot |

Regole e semantica:

1. **Validazione completa prima di toccare qualcosa**: un campo non valido annulla l'intera richiesta (`bad_params`, `value_out_of_range`, `unencodable_text`); `stale_ref` se `ref`/`expect` non coincidono.
2. **Testi**: UTF-8 convertito in latin-1 (`unencodable_text` se non rappresentabile); lunghezze massime = quelle del record di rent del gioco (127/127/255 byte): il gioco copia i testi con `strcpy` senza controllo e un
   testo piu' lungo corromperebbe la memoria al salvataggio. Niente caratteri di controllo (neppure `\n`: il gioco aggiunge i terminatori), niente `$` (codici colore e sostituzioni del gioco) e niente `~`
   (terminatore delle stringhe nei file del mondo). A differenza di `echo`, qui `$` non viene neutralizzato con un escape ma **rifiutato**: il testo resta salvato nel rent e usato per cercare l'oggetto per parole chiave, un escape
   resterebbe visibile come `\$`.
3. **Memoria** (profilo dikumod): le stringhe di un'istanza sono copie allocate e di sua proprieta'; il MUD ne alloca una nuova e libera la vecchia **solo** se non appartiene al prototipo ([regola esatta](../adapters/dikumod-live.md#testi-di-un-oggetto-istanza)).
4. **Oggetto indossato**: il MUD toglie temporaneamente i bonus dell'oggetto, applica la patch e li ripristina senza rieseguire i controlli di indossabilita' (allineamento, classe): l'oggetto non cade a terra e il personaggio mantiene
   coerenti punti, abilita' e peso trasportato.
5. **Peso**: il `weight` dell'oggetto cambia di un delta; lo stesso delta e' applicato ai contenitori che lo contengono e al peso trasportato dal giocatore.
6. Con `save: true` il giocatore e' salvato con la stessa procedura di `player.set`. Il rent salva `name`, `short_description`, `description`, i valori, `extra_flags`, `weight`, `timer`, `bitvector` e gli affect; `cost` e `wear_flags` tornano quelli
   del prototipo al login (per questo non sono modificabili).

Risposta: `{"name", "fp", "saved", "warnings", "item"}`, con `item` come in `obj.get` dopo la modifica e `fp` la nuova impronta (il `ref` resta valido). Non e' idempotente in senso stretto ma ripetere la stessa patch con la nuova `expect`
produce lo stesso stato; dopo un timeout il client rilegge con `obj.get`. Audit: comando, giocatore, `ref`, nomi dei campi.

### `obj.remove`

Classe `write`, feature `inventory`. Parametri: `name`, `ref`, `expect` (obbligatorio), `save` (default `true`). Estrae l'oggetto dal giocatore e lo **distrugge**; se e' un contenitore distrugge anche tutto il suo contenuto, a qualunque livello.
Pesi dei contenitori e peso trasportato sono aggiornati dal gioco. Risposta `{"name", "removed": true, "destroyed": <oggetti del primo livello distrutti, contenitore compreso>, "saved", "warnings"}`. Non idempotente: un secondo tentativo con lo stesso `ref`
e' `stale_ref`. L'operazione non si annulla.

### Contratto per l'editor (inventario)

Lato editor (realizzato: rotte in [contratto live](contract-live.md#inventario-e-oggetti-istanza), `LiveAdapter.live_player_inventory|live_item_get|live_item_set|live_item_remove`, dialogo del giocatore e pannello «Server live»): il pannello dell'inventario di un giocatore connesso legge `player.inventory` e mostra l'albero (profondita' e `slot`);
a ogni scrittura (`obj.set`, `obj.remove`) invia `ref` e `expect` presi dall'ultima lettura **della stessa riga**; su `stale_ref` ricarica l'elenco e avvisa l'utente senza ripetere; mostra sempre `warnings` (`vnum_not_saveable`
di `load.obj`, `save_failed`); chiede conferma esplicita per `obj.remove` (azione distruttiva, il contenitore porta con se' il contenuto); non consente di scrivere un testo con `$`, `~` o oltre i limiti (li ricava da questa
pagina e da `hello.limits`, non li inventa); abilita i comandi in base a `hello.commands` e `hello.features`, quindi con le scritture spente mostra l'inventario in sola lettura. Solo superuser, come le altre rotte `live`.

### Comandi riservati e non definiti

`server.shutdown`, `server.reboot` (o `copyover`), `player.kick`, `exec`, `force`, qualunque comando che passi una stringa
all'interprete del gioco: **non fanno parte della v1**. I primi tre potrebbero essere definiti in una versione futura nella
classe `danger`, con una conferma esplicita nella richiesta e una abilitazione separata; gli ultimi due non saranno mai definiti.

## Esempio completo di sessione

Il client apre il socket, poi (una riga per messaggio; `>` client -> server, `<` server -> client):

```
> {"id":1,"cmd":"hello","params":{"protocols":[1],"token":"…","client":"pachimudeditor/0.2.0","actor":"mario.rossi"}}
< {"id":1,"ok":true,"result":{"protocol":1,"mud":{"kind":"dikumod","name":"LeU","version":"1.7.0 cdrom","module":"livectl 0.1"},"limits":{"max_line":4096,"max_response":65536,"max_pending":8,"request_timeout_ms":2000,"max_text":400},"features":[],"commands":{"ping":{"class":"read"},"who":{"class":"read"},"player.get":{"class":"read","fields":["gold","exp"]},"player.set":{"class":"write","fields":["gold","exp"]}}}}
> {"id":2,"cmd":"who","params":{"limit":10}}
< {"id":2,"ok":true,"result":{"players":[{"name":"Mario","state":"playing","level":34,"room":3001,"zone":4}],"count":1,"truncated":false}}
> {"id":3,"cmd":"player.set","params":{"name":"mario","set":{"gold":99999,"exp":-5}}}
< {"id":3,"ok":false,"error":{"code":"value_out_of_range","message":"exp fuori intervallo","params":{"field":"exp","min":0,"max":2147483647}}}
> {"id":4,"cmd":"player.set","params":{"name":"mario","set":{"gold":99999}}}
< {"id":4,"ok":true,"result":{"name":"Mario","applied":{"gold":{"old":1500,"new":99999}},"saved":true,"warnings":[]}}
> {"id":5,"cmd":"exec","params":{"line":"shutdown"}}
< {"id":5,"ok":false,"error":{"code":"unknown_command","message":"comando sconosciuto"}}
```

(Il `token` e' omesso: nei log e nella documentazione si scrive sempre `…`.)

## Compatibilita' e versioni

- `protocol` e' un intero. Dentro una versione sono ammessi solo cambi **additivi**: nuovi comandi, nuovi campi nelle risposte, nuovi
  valori in `features`. Il client DEVE ignorare chiavi sconosciute nelle risposte e valori di `error.code` che non conosce (li tratta come errore generico).
- Il server e' **severo** sulle richieste (chiavi sconosciute in `params` -> `bad_params`): un nuovo parametro facoltativo di un
  comando esistente si annuncia in `hello` (es. `commands["who"].params`) e il client lo usa solo se presente. Cosi' un editor nuovo
  non fa cambiare comportamento di nascosto a un modulo vecchio.
- Un cambio incompatibile (campi tolti o significato diverso) e' una nuova versione intera; il server puo' parlarne piu' d'una e
  sceglie la piu' alta in comune.
- I nomi dei comandi e dei campi giocatore sono stabili; i testi dei messaggi no.
- Il modulo di un MUD dichiara il proprio profilo in `mud.kind`; i comandi e i campi realmente disponibili sono quelli di `hello`, non
  quelli di questa pagina.

## Lato editor (implementato, SDK 1.5)

L'editor e' il client di riferimento. Contratto HTTP: [canale live, rotte](contract-live.md).

- **SDK** (`pachimudeditor.sdk`): mixin opzionale `LiveAdapter` (capability `supports_live`), DTO neutri (`LiveStatus`, `LiveWho`, `LiveServerInfo`, `LiveZones`, `LivePlayerState`, `LivePlayerSetIn/Out`, `LiveZoneResetIn/Out`, `LiveLoadIn/Out`, `LiveEchoIn/Out`),
  `LiveError` (codice del protocollo o locale: `unreachable`, `timeout`, `outcome_unknown`, `token_missing`, `response_too_large`, ...) e `LiveClient`, il client asincrono riusabile dagli adapter.
- **Client**: una connessione per mondo (socket Unix), richieste serializzate da un lock, `hello` con token letto dall'ambiente a ogni connessione, riconnessione **pigra** a ogni richiesta (un MUD spento non e' un errore dell'editor),
  rispetto di `max_line` (richiesta troppo grande = errore locale, non inviata) e `max_response` (risposta o flusso senza `\n` troppo grande = errore e connessione chiusa), un comando non dichiarato da `hello` non viene inviato.
  Le letture si ritentano una volta se la connessione era caduta; le scritture **mai** dopo l'invio (timeout o caduta = `outcome_unknown`). Una scrittura con un `actor` diverso da quello della connessione la riapre,
  cosi' l'audit del MUD registra l'utente dell'editor (nome dichiarato, non prova d'identita'). Nessun circuit breaker: il tentativo su un socket assente costa pochi microsecondi.
  `idempotency_key` non viene mai inviata (il modulo di riferimento non la dichiara in `features`).
- **Permessi**: tutte le rotte solo **superuser**; capability `supports_live`; scritture anche con mondo non `read_only`.
- **Percorso di un giocatore** (dikumod): connesso e `playing` con canale scrivibile = modifica live; non connesso = file; canale spento = file (con la conferma «server acceso» solo se il server e' rilevato); `auth_failed` = errore chiaro
  (`worldlive.auth_failed`), nessun ripiego silenzioso nelle rotte live. Un giocatore connesso scritto **su file** richiede `confirmServerRunning`; il caso di un non connesso a server acceso resta l'avviso best-effort (corsa possibile
  tra il controllo e la scrittura: vedi i rischi).

Configurazione del mondo (`params.live`, nel yaml; il segreto sta nel `.env` / ambiente):

```yaml
webeditor_worlds:
  - id: dikumod
    kind: dikumod
    path: /percorso/dikumod/lib
    read_only: false                                 # le scritture live richiedono un mondo non read_only
    params:
      live:
        socket: /percorso/dikumod/livectl.sock      # ASSOLUTO, al massimo 107 byte (sun_path)
        token_env: DIKUMOD_LIVE_TOKEN               # NOME della variabile d'ambiente, mai il valore
        timeout_ms: 3000                            # 200..60000, default 3000
        enabled: true                               # false = canale spento senza togliere la configurazione
```

All'avvio `validate` rifiuta parametri incoerenti (percorso relativo o troppo lungo, `token_env` non valido, timeout fuori scala, chiavi sconosciute -- anche un `token` scritto per errore --, `transport: tcp`
non supportato dall'editor) ma **non** controlla che il socket esista o che il MUD sia acceso, e non fallisce se la variabile del token manca (lo stato del canale dira' `token_missing`).

## Client da riga di comando

Stato: **implementata** (`src/pachimudeditor/cli/commands/live.py`, test in `tests/live/test_cli.py` contro finto server e MUD reale). Comandi `pachimudeditor live`, un client sottile dello stesso protocollo per script esterni. Il superuser vale per le **rotte HTTP**
dell'editor; per la CLI vale il possesso del token e dell'accesso al socket (stessi permessi del file del socket e di `.env`).

```
pachimudeditor live [--world ID | --socket PATH] [--token-env VAR] [--timeout SECONDI] [--actor NOME] [--pretty] <comando> [argomenti]
```

- **Dove sta il canale**: `--world ID` legge `params.live` del mondo (socket, `token_env`, timeout) dalla configurazione dell'editor (`--workdir` come gli altri comandi);
  in alternativa `--socket PATH` (assoluto). Il **token** si legge **solo** dalla variabile d'ambiente `--token-env` (default `PACHIMUDEDITOR_LIVE_TOKEN`, oppure il
  `token_env` del mondo) e dal `.env` della cartella di lavoro: **mai** come argomento (comparirebbe in `ps` e nella cronologia della shell).
- `--actor` va nell'`hello` (default `cli:<utente unix>`); `--timeout` default 5 s.
- Non chiede mai conferme interattive: la conferma per gli immortali e' il flag `--confirm-immortal`.

| Comando | Equivale a |
|---|---|
| `live status` | `hello` + `ping` (+ `info`): `{"connected": true, "protocol": 1, "mud": {...}, "commands": [...]}` |
| `live ping`, `live info` | `ping`, `info` |
| `live who [--prefix P] [--limit N] [--no-linkdead]` | `who` |
| `live player get NOME` | `player.get` |
| `live player set NOME CAMPO=VALORE... [--no-save] [--confirm-immortal]` | `player.set` (`gold=500`, `conditions.drunk=0`, `levels.warrior=40`) |
| `live zone list` | `zone.list` |
| `live zone reset (--zone N \| --room VNUM) [--only-if-empty]` | `zone.reset` |
| `live load mob VNUM (--room VNUM \| --player NOME) [--count N] [--notify]` | `load.mob` |
| `live load obj VNUM (--room VNUM \| --player NOME) [--count N] [--notify]` | `load.obj` |
| `live echo TESTO (--all \| --player NOME \| --room VNUM)` | `echo` |
| `live player inventory NOME [--brief] [--limit N]` | `player.inventory` (feature `inventory`) |
| `live obj get NOME REF [--fp FP [--vnum V]]` | `obj.get` (con `--fp` verifica anche `expect`) |
| `live obj set NOME REF --fp FP [--vnum V] CAMPO=VALORE... [--no-save]` | `obj.set` (`name=...`, `short_description=...`, `description=...`, `weight=3`, `extra_flags=5`, `timer=600`, `values.0=7`, `affects.1.location=13 affects.1.modifier=2`) |
| `live obj remove NOME REF --fp FP [--vnum V] [--no-save]` | `obj.remove` (distrugge l'oggetto e il contenuto) |

**Output**: sempre **un solo documento JSON** su stdout (compatto, una riga; indentato con `--pretty`), anche per gli errori, cosi' uno script lo
elabora con `jq` senza dover separare stderr: `{"ok": true, "result": {...}}` oppure `{"ok": false, "error": {"code": "...", "message": "...", "params": {...}}}`
(gli stessi `code` stabili del protocollo; per i fallimenti locali `code` vale `connection_failed`, `auth_failed`, `outcome_unknown`, `usage`). Stderr resta per la diagnostica umana (mai il token).

| Exit code | Significato |
|---|---|
| 0 | successo |
| 1 | il MUD ha risposto con un errore (`ok: false`): comando valido ma rifiutato (`not_found`, `value_out_of_range`, `forbidden_by_policy`, ...) |
| 2 | uso errato o configurazione incompleta (argomenti, token mancante, mondo senza `params.live`) |
| 3 | canale non raggiungibile (socket assente, connessione rifiutata, timeout prima dell'invio) |
| 4 | autenticazione o negoziazione fallite (`auth_failed`, `protocol_unsupported`, `rate_limited` sul `hello`) |
| 5 | esito sconosciuto: timeout o connessione persa **dopo** l'invio di un comando di scrittura (non ritentare senza verificare con `player get` / `who`) |

I comandi di scrittura non vengono mai ritentati automaticamente.

Scelte dell'implementazione dove la specifica lasciava margine (sempre la via piu' conservativa):

- `--world` e `--socket` sono **mutuamente esclusivi** e uno dei due e' obbligatorio; `--socket` deve essere assoluto; un mondo con `enabled: false` o senza `params.live` e' exit 2. `--token-env` prevale sul `token_env` del mondo; vuole un **nome** di variabile (un valore che non lo sia e' rifiutato senza stamparlo).
- Timeout: `--timeout` esplicito, altrimenti `timeout_ms` del mondo, altrimenti 5 s.
- Token: prima l'ambiente, poi il `.env` della cartella di lavoro; mai da argomenti. Il token viene anche rimosso (`***`) da qualunque testo stampato.
- Ogni comando fa prima l'`hello`: i suoi fallimenti sono exit 3 (socket assente, timeout) o 4 (`auth_failed`, `protocol_unsupported`, `rate_limited`, `too_many_connections`, risposta non valida); gli errori **dopo** il handshake sono exit 1, salvo `unreachable`/`timeout` di una lettura (3) e `outcome_unknown` di una scrittura (5).
- Un comando non dichiarato da `hello` (classe `write` disattivata) non viene inviato: `command_disabled`, exit 1.
- `live status` fa `hello` + `ping` (senza `info`, che resta in `live info`). `idempotency_key` non viene mai inviata (il client condiviso non la implementa e le scritture non si ritentano).
- `CAMPO=VALORE`: i valori che sembrano interi sono numeri, il resto stringhe (la validazione e' del MUD); `a.b=v` diventa `{"a": {"b": v}}`. Salva di default (`--no-save` per non salvare).
- `obj set|remove`: `ref` e `--fp` (e `--vnum`, assente = `null`) vengono dall'ultima lettura (`player inventory`); `--fp` e' obbligatoria (senza, exit 2). `values.N` e `affects.N.location|modifier` costruiscono gli array con `null` nelle posizioni non indicate (ogni affect vuole `location` e `modifier`); i testi sono sempre stringhe; `stale_ref` e' exit 1.
- `who` invia solo i filtri dati (`prefix`, `limit`, `linkdead:false` con `--no-linkdead`); `zone reset`, `load`, `echo` richiedono **esattamente una** destinazione, altrimenti exit 2.
- Gli errori di sintassi rilevati da typer/click (argomento mancante o sconosciuto) escono con 2 ma con il testo standard su stderr, non in JSON.

## Rischi aperti e decisioni

### Rischi

1. **Il modulo C e' parte del gioco.** Un bug (parser, puntatori) fa cadere il MUD. Mitigazione: modulo piccolo, parser compilabile e
   fuzzabile separatamente dal gioco, test con input ostili prima di ogni uso, interruttore di emergenza (file `livectl.disable`
   controllato all'avvio, canale in sola lettura per default).
2. **Editor compromesso = potere sul gioco** entro la allowlist (oro, esperienza, mob, oggetti). Il canale non puo' distinguere un
   utente legittimo dell'editor da un attaccante che ha rubato la sessione. Mitigazioni: permessi dell'editor, audit lato MUD, classi.
3. **Divergenza memoria/file.** Una modifica live non salvata sparisce con un crash; una salvata ma seguita da una scrittura su file
   dello stesso giocatore viene persa o sovrascritta. Regola: un giocatore connesso si modifica solo dal canale.
4. **Corsa file/login.** Tra «non e' connesso» e la scrittura su file il giocatore puo' collegarsi. Possibile soluzione futura: un
   comando di blocco temporaneo del login per nome (non in v1).
5. **Semantica di «effettivo» e «base».** Alcuni valori in memoria includono equipaggiamento e incantesimi, quelli nel file no
   (vedi [profilo dikumod](../adapters/dikumod-live.md#campi-modificabili-live)). Per questo i campi derivati non sono modificabili in v1.
6. **Regole di bilanciamento del gioco** (deny-list di oggetti, divieto di creare immortali) vivono nei comandi degli immortali, non nelle
   funzioni di basso livello: il canale deve ripeterle, e potrebbero divergere nel tempo.
7. **Dati personali.** `who` non espone l'indirizzo di rete; l'audit contiene nomi di giocatori e valori numerici.
8. **Ogni MUD C ha il proprio modulo.** Il protocollo e' uguale, gli innesti no. Per basedmud (ROM/QuickMUD) gli innesti non sono stati
   ancora cercati nei sorgenti: **da verificare**.
9. **Token a riposo.** Chi puo' leggere l'ambiente del processo del MUD o il `.env` dell'editor ha il canale: stessi permessi del `.env`.

10. **Oggetti istanza.** Le strutture degli oggetti sono puntatori a liste concatenate, con stringhe allocate e pesi cumulativi: un errore nel modulo corromperebbe memoria del gioco. Mitigazioni: nessun puntatore tra due richieste (`ref` come percorso + impronta), validazione completa prima di applicare, lunghezze dei testi pari ai record di rent, rifiuto degli oggetti in stato incoerente, nessun reindossamento tramite le funzioni con controlli. Restano rischi di bilanciamento (un `obj.set` puo' creare oggetti arbitrari) e di concorrenza con il salvataggio: una modifica non salvata si perde al crash.
11. **Rent e vnum.** Il rent salva il vnum a 16 bit: un oggetto con vnum > 32767 portato da un giocatore si corrompe al salvataggio (avviso `vnum_not_saveable` in `load.obj`). I testi piu' lunghi del record di rent corromperebbero memoria: per questo i limiti.

### Decisioni prese

1. **Token** del MUD in variabile d'ambiente `LIVECTL_TOKEN` (cancellata dopo la lettura); lato editor `token_env`.
2. **Permessi**: le rotte `live` dell'editor solo per superuser.
3. **`levels`** modificabile live; promuovere a un livello >= 51 richiede `confirm_immortal: true` (avvertenza + sblocco esplicito, vedi [`player.set`](#playerset)).
4. **Comandi `danger`** (arresto, riavvio, kick): fase 2, fuori dalla v1.
5. **`save`** di `player.set` vale `true` di default (scelta conservativa: lo stato in memoria e quello su file restano allineati).
6. **Deny-list di `load.obj`**: replicata quella di `do_oload` (default del modulo, configurabile con `LIVECTL_DENY_OBJ`).
7. **`idempotency_key`**: feature opzionale, annunciata in `features` solo se il modulo la implementa (il modulo di riferimento non la implementa: `features` e' vuoto).
8. **Client**: il protocollo e' indipendente dall'editor; il token autentica qualunque client. L'editor e' il client di riferimento, la CLI `pachimudeditor live` un client sottile ([specifica](#client-da-riga-di-comando)); per la CLI vale il possesso di token e socket, il superuser vale per le rotte HTTP.
9. **pachimud**: componente `asyncio` nello stesso processo con lo stesso protocollo, **previsto** come passo successivo a dikumod (solo descritto qui).
10. **Inventario live** (v1.1, feature `inventory`): `player.inventory`, `obj.get`, `obj.set`, `obj.remove`; `ref` come percorso + `expect` obbligatorio nelle scritture; testi senza `$`/`~` e entro i limiti del rent; vedi il [profilo](../adapters/dikumod-live.md#inventario-e-oggetti-istanza).
11. **Un solo MUD C per ora**: Diku Modificato nella variante DikuMod1 (sorgenti nella cartella ufficiale `/dati/luca/muds/leu`); altre varianti e basedmud non sono coperti.
