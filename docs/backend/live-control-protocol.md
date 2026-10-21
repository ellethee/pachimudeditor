# Canale di controllo live (protocollo `livectl`)

**Stato: specifica, non implementata.** Descrive un canale tra l'editor e un MUD **in esecuzione**: l'editor chiede informazioni
(chi e' connesso, stato del server) e fa modifiche immediate (giocatori connessi, reset di zona, creazione di mob/oggetti,
messaggi) senza fermare il gioco e senza toccare i file. Il caso di riferimento e' Diku Modificato ([profilo dikumod](../adapters/dikumod-live.md));
per pachimud (Python) lo stesso protocollo sarebbe servito da un componente `asyncio` nello stesso processo.

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
| L'editor (backend) | si', **come unico client** | autentica gli utenti e applica i permessi; il MUD non conosce gli utenti dell'editor |
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
   il danno ma non lo annulla (vedi [rischi aperti](#rischi-aperti-e-domande-aperte)).
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
- profondita' massima 4, al massimo 32 chiavi per oggetto, stringhe fino a 512 byte, array fino a 32 elementi;
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
  "features": ["who.paging"],
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
    "echo":       {"class": "write"}
  }
}}
```

**Capability discovery**: l'editor costruisce l'interfaccia da `commands` e `fields` e non da una versione del MUD. Un comando assente
da `commands` (non implementato, classe disattivata o fuori allowlist) NON DEVE essere inviato; se lo e' risponde `unknown_command` o
`command_disabled`. `features` e' un elenco di stringhe per estensioni opzionali dello stesso protocollo (es. `idempotency_key`).

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
- Lato MUD: letto all'avvio da un **file** con permessi `0600` (`livectl.token`, percorso nella configurazione del modulo) oppure dalla variabile
  d'ambiente `LIVECTL_TOKEN`; il file e' preferito (l'ambiente e' leggibile in `/proc/<pid>/environ` e spesso finisce nei log
  degli script di avvio). Se il file ha permessi piu' larghi di `0600`, il token manca o e' corto, il modulo **non si attiva** e
  lo scrive nel log del gioco (il gioco parte comunque, senza canale).
- Lato editor: il yaml del mondo contiene solo il **nome** della variabile (`token_env`), il valore sta nel `.env` della cartella
  di lavoro (regola gia' valida per i segreti: [configurazione](../guide/configuration.md)). Il token NON DEVE comparire nel yaml, nei log, nelle
  eccezioni, nelle risposte API, nei campi `error`, nell'audit, nella cronologia dei comandi.
- Il confronto avviene a **tempo costante** (nessuna uscita anticipata al primo byte diverso, anche con lunghezze diverse).
- Rotazione: cambiare il token nel file del MUD e nel `.env` dell'editor; il MUD rilegge il file con un segnale dedicato o al riavvio
  (da decidere nel profilo); le connessioni gia' autenticate restano valide fino alla chiusura.
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
   "race": "human", "sex": "male", "room": 3001, "zone": 4, "position": "standing",
   "fighting": false, "idle_s": 12, "immortal": false, "invisible": 0}
 ],
 "count": 1, "truncated": false}
```

`state`: `playing`, `linkdead`, `polymorph` (il personaggio e' trasformato: `name` e' quello reale). Non compaiono i collegamenti
ancora in login. L'indirizzo di rete NON e' mai nella risposta (dato personale). I nomi dei campi di dettaglio sono quelli del
profilo; i valori testuali (razza, classe, posizione) sono i nomi canonici delle tabelle del formato.
Effetti collaterali: nessuno. Idempotente. Ordine: lista del gioco (non garantito stabile).

### `player.get`

Classe `read`. Parametri: `name`. Risposta: `{"name", "state", "fields": {...}}` con i campi dichiarati in `hello` (`commands["player.get"].fields`),
**valori correnti in memoria** (possono differire dal file finche' non c'e' un salvataggio). Errori: `not_found` (nessun
giocatore con quel nome nel mondo), `player_not_playing`. Effetti collaterali: nessuno. Idempotente.

### `player.set`

Classe `write`. Parametri: `name`, `set` (oggetto campo -> valore, da 1 a 16 campi), `save` (bool facoltativo, default `true`). Risposta:

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
creabili a mano (il gioco ne ha una per il comando degli immortali): vnum in lista -> `forbidden_by_policy`. Non idempotente.

### `echo`

Classe `write`. Parametri: `text` (1..`max_text` byte), `to` (oggetto con **una sola** chiave: `all` (`true`), `player` (nome), `room` (vnum)). Risposta
`{"recipients": 12}`. `all` raggiunge i giocatori in stato `playing`. Il testo e' neutralizzato come descritto in [validazione e testi](#validazione-e-testi). Non idempotente.

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

## Lato editor (descrizione, non implementato)

Una capability dell'SDK, `LiveAdapter` (mixin opzionale come `PlayersAdapter`), con flag `supports_live_control`:

| Metodo (async) | Compito |
|---|---|
| `live_info()` (sincrono, nessun I/O) | descrittore: comandi attesi, etichette i18n, campi modificabili dichiarati in `hello` |
| `live_status()` | prova di connessione (`hello` + `ping`), mai blocca oltre il timeout; esito `connected / unreachable / auth_failed` |
| `live_who()`, `live_player_get(name)`, `live_player_set(name, fields)` | giocatori connessi |
| `live_zone_reset(zone)`, `live_load(...)`, `live_echo(...)` | azioni di servizio |

Rotte neutre del core sotto `/api/world/live/...` (envelope e codici come il [contratto API](contract.md); 409 `world.capability_missing`
senza capability; errori del canale mappati sui codici di questa pagina con prefisso `live.`). **Permessi**: sono operazioni con effetto immediato sul
gioco e oggi l'editor non ha permessi per mondo ([sicurezza](../guide/security.md#modello-dei-permessi-per-utente)); le rotte `live` DOVREBBERO richiedere
almeno superuser, o un permesso dedicato (domanda aperta).

Scelta del percorso nell'adapter, per un giocatore:

| Situazione | Percorso |
|---|---|
| canale raggiungibile e `who` lo mostra connesso | **live** (`player.set`) |
| canale raggiungibile e il giocatore **non** e' connesso | **file** (modifica L3); il flag di conferma «server acceso» non e' piu' necessario per quel giocatore |
| canale non raggiungibile e server forse acceso | **file** con il flag di conferma attuale |
| canale dichiarato ma `auth_failed` | errore chiaro all'utente, nessun ripiego silenzioso sui file |

Il ripiego sui file con server acceso e canale presente resta soggetto a una corsa (il giocatore puo' collegarsi tra il controllo e
la scrittura): vedi i rischi.

Configurazione del mondo (`params`, nel yaml; il segreto sta nel `.env`):

```yaml
webeditor_worlds:
  - id: dikumod2
    kind: dikumod
    path: /percorso/dikumod2/lib
    read_only: false
    params:
      live:
        transport: unix                              # unix (default) | tcp
        socket: /percorso/dikumod2/lib/livectl.sock  # per tcp: host: 127.0.0.1, port: 9001
        token_env: DIKUMOD2_LIVE_TOKEN               # NOME della variabile in .env, mai il valore
        timeout_ms: 3000
```

Il client dell'editor mantiene una connessione, serializza le richieste, riconnette con backoff, interrompe i tentativi dopo ripetuti
errori (circuit breaker), passa `actor` = utente autenticato nell'`hello`, scrive il proprio audit e non ritenta le operazioni non idempotenti.

## Rischi aperti e domande aperte

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
9. **Token a riposo.** Chi legge il file del token ha il canale: stessi permessi del `.env` dell'editor.

### Domande per l'utente

1. Il token del MUD in **file `0600`** (consigliato) o in variabile d'ambiente?
2. Le rotte `live` dell'editor solo per **superuser**, oppure un permesso dedicato per mondo (`world.<id>.live`)?
3. `levels` modificabile live? Il gioco vieta di creare immortali (livello >= 51) ai non implementatori: replicare il divieto (consigliato) o niente limite?
4. `save` di default **vero** in `player.set` (consigliato) o la modifica resta in memoria finche' qualcuno salva?
5. Deny-list dei vnum di `load.obj`: replicare quella del comando degli immortali (oggetti privati 150-199 e pochi altri) o lista vuota?
6. Comandi `danger` (arresto, riavvio): mai nel canale, oppure in una fase 2 con secondo segreto e conferma? E' prevista anche `player.kick`?
7. `idempotency_key` gia' nella v1 o rimandata?
8. Dikumod2: i sorgenti completi non sono nella cartella (solo 4 file); il modulo si scrive su DikuMod1/LeU e si prova su una build di
   dikumod2 ricostruita?
9. Il canale e' per il **solo** editor o anche per uno script di amministrazione da riga di comando (stesso protocollo, token separato)?
10. Il MUD pachimud: componente `asyncio` nello stesso processo con lo stesso protocollo: confermato come passo successivo?
