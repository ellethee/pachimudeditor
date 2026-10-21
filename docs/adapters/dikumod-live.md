# Diku Modificato: profilo del canale live

**Stato: implementato (modulo C di riferimento in `adapters/dikumod/mud-module/`, provato su una copia del gioco; lato editor: adapter `params.live`, rotte `/api/world/live` e pagina Giocatori, provati contro il MUD reale su una copia).** Applica il [protocollo `livectl`](../backend/live-control-protocol.md) a Diku Modificato: dove si
aggancia il modulo C nel sorgente, quali funzioni del gioco usano i comandi, quali campi si possono cambiare a gioco acceso e quali
insidie ci sono. Il protocollo (trasporto, sicurezza, comandi, errori) e' in [canale di controllo live](../backend/live-control-protocol.md);
qui c'e' solo cio' che dipende dal sorgente.

Tutto quello che segue e' stato letto nel sorgente indicato; dove non e' stato possibile verificare e' scritto **da verificare**.
I numeri di riga sono di DikuMod1, cartella ufficiale `/dati/luca/muds/leu` (`src/`), e possono scorrere.

## Sorgenti esaminati

| Albero | Contenuto | Uso in questo profilo |
|---|---|---|
| `/dati/luca/muds/leu/src` | sorgenti completi (57 file `.c`, ~97 000 righe), porting x86_64 con g++; `Makefile` nella radice, binario `bin/leu` | riferimento (DikuMod1, «dikumod») |

Il gioco e' scritto in C ma e' **compilato come C++** (`g++ -fpermissive -std=gnu++98 -fno-operator-names -w`, `-DNETBSD -DLINUX -DNO_RENT_COST`; `Makefile`
`CC=g++`): il modulo nuovo deve compilare cosi', quindi niente inizializzatori designati ne' VLA e attenzione ai nomi riservati del C++
(`new`, `class`, ...). I dati su disco usano il layout storico i386 (`char_file_u` 3036 byte,
[formato](../formats/dikumod.md#9-file-giocatore-e-rent)); `EMANUELE` e' definito in `structs.h` (riga 81).

## Il ciclo principale

`main` (`comm.c` riga 389) legge gli argomenti, fa `chdir` nella cartella dati (riga 506: da qui in poi i percorsi relativi sono relativi
a `lib/`), poi `run_the_game(port)` (riga 540):

```
run_the_game:  init_socket -> signal_setup -> boot_db -> game_loop(s) -> close_sockets
game_loop:     while (!mudshutdown) {   // una iterazione = un "pulse"
                 FD_SET dei descrittori; gettimeofday
                 [EMANUELE] select() di sola attesa per OPT_USEC (250 ms) , poi select() di poll con timeout 0
                 new_descriptor / close dei descrittori in errore / process_input
                 per ogni descrittore: un comando dalla coda (command_interpreter, nanny, editor...)
                 process_output, prompt
                 pulse++  e gli eventi periodici (zone_update, River, Teleport, violence, weather/affect_update)
                 tics++   SetStatus(STATUS_ENDLOOP)
               }
```

- Un'iterazione dura **250 ms** (`OPT_USEC`, riga 40: «4 passes/sec»). Il commento in `game_loop` dice che `pulse` cambia ogni quarto di
  secondo; `pulse` e' un `int` che riparte da 0 a 2400 (riga ~1041). Per il contatore monotono del protocollo (`ticks`) serve un contatore del modulo.
- Con `EMANUELE` (il caso reale) il ciclo dorme **all'inizio** dell'iterazione (`select(0,...)` con timeout, ripetuto su `EINTR`) e poi fa il poll
  non bloccante. Quindi il gioco e' fermo in `select` per la maggior parte del tempo: un poll in piu' per iterazione costa poco.
- Il server e' a **thread singolo** (nessun `pthread`, nessun `fork()`: verificato con grep; `system()` sì, in `interpreter.c` e `db.c`).
  Non ci sono `continue` nel ciclo: ogni iterazione arriva a `tics++` (riga 1048).

### Punti di innesto

| # | Dove | Riga | Cosa |
|---|---|---|---|
| 1 | `run_the_game`, subito **dopo** `boot_db();` e prima di `game_loop(s);` | 568-572 | `livectl_init();` legge la configurazione, crea il socket, azzera lo stato. Dopo `boot_db` perche' servono le tabelle del mondo; dopo `chdir`, quindi il percorso del socket nella configurazione deve essere **assoluto** |
| 2 | `game_loop`, in coda all'iterazione, **prima** di `SetStatus( STATUS_ENDLOOP, NULL );` e dopo `tics++;` | 1048-1049 | `livectl_poll();` serve accept/lettura/esecuzione/scrittura con il budget del protocollo |
| 3 | pulizia | - | `atexit(livectl_shutdown)` chiamato da `livectl_init()`: nessuna modifica a `run_the_game`. Chiude i client e rimuove il file del socket nell'uscita ordinata (`return` da `main`). Uscite con `abort()` (checkpoint, `assert`) non passano di qui: il socket residuo e' gestito all'avvio successivo (rilevamento con `connect()`) |

Perche' in coda all'iterazione: `next_to_process` e i puntatori `next_point` dei cicli sui descrittori sono variabili locali o ricalcolate a
ogni iterazione; a fine iterazione nessun ciclo e' in corso e le liste (`descriptor_list`, `character_list`, persone nelle stanze) sono
coerenti. Il poll in testa (subito dopo il `select`) sarebbe ugualmente sicuro ma verrebbe prima dell'elaborazione dell'input dei giocatori
della stessa iterazione: nessun vantaggio.

Il modulo NON usa `select` ne' `FD_SET` del gioco: `maxdesc` e i `fd_set` sono del gioco e `FD_SETSIZE` (1024) e' un limite; il canale usa
`poll()` con timeout 0 su descrittori propri. Il gioco chiude i descrittori dei giocatori con `close_socket`: il modulo non li tocca.

`signal_setup` installa: `SIGPIPE` ignorato (le scritture su un client scollegato non terminano il processo, comunque il modulo usa
`MSG_NOSIGNAL`), `SIGUSR2` arresto, `SIGHUP/SIGINT/SIGTERM` salvataggio generale e riavvio (`hupsig`, che fa `raw_force_all("save")` **dentro il gestore**: gia' fragile, non
dipende dal modulo), `SIGALRM` ignorato e un timer `ITIMER_VIRTUAL` di 5 minuti di CPU con `checkpointing` che fa `abort()` se `tics` non e' stato
incrementato: il poll non deve mai bloccare il ciclo (e non lo fa).

## Stato del gioco: dove stanno i giocatori

| Cosa | Dove (sorgente) | Note |
|---|---|---|
| connessioni | `struct descriptor_data *descriptor_list` (`comm.c` 59), lista concatenata con `->next` (`structs.h` 1542) | un nodo per socket, anche in login |
| personaggio di un descrittore | `d->character`, `d->original` (non nullo se il giocatore e' trasformato o e' un immortale in switch), `d->connected` | `CON_PLYNG` (0) = in gioco; altri valori = login, menu, editor (`CON_EDITING`, `CON_OBJ_EDITING`, `CON_MOB_EDITING`), `CON_LDEAD` ... |
| tutti i personaggi (giocatori e mob) | `struct char_data *character_list`, `->next` (usata da `do_who`, `act.info.c` 2759) | include i giocatori con **link morto** (`ch->desc == 0`; `IS_LINKDEAD`, `utility.c` 4648) |
| personaggio | `struct char_data` (`structs.h` 1240) | `player` (nome, livelli `level[ABS_MAX_CLASS]`, `iClass`, titolo, sesso), `abilities` (base) e `tmpabilities` (effettivi), `points`, `specials`, `skills`, `equipment[MAX_WEAR]`, `carrying`, `in_room` (vnum), `desc` |
| stato di gioco | `d->str != NULL` (editor di testo), `d->showstr_point` (paginazione), `ch->specials.fighting`, `GET_POS(ch)` | `command_interpreter` e' chiamato solo se `connected == CON_PLYNG && !showstr_point` e `str == NULL` |
| stanze e zone | `real_roomp(vnum)` (inline in `utils.h` 342), `room_data.zone` (indice di zona); `zone_table[]` con `top_of_zone_table` (`db.h` 61, `db.c` 40) | `zone_data`: `name`, `num`, `lifespan`, `age`, `top`, `start`, `reset_mode`, `cmd` |
| prototipi | `mob_index[]`, `obj_index[]` (`db.h` 88: `iVNum`, `number` = istanze vive, `pos`, `name`) con `top_of_mobt`, `top_of_objt` | `real_mobile(vnum)` / `real_object(vnum)` (`db.c` 4218/4253) restituiscono l'indice o -1 |
| tempo | `long Uptime` (`comm.c` 72, impostato in `main`), `int pulse`, `GetLagIndex()` (`act.info.c`) | |
| contatori | `mob_count`, `obj_count`, `room_count` (`db.c` 47-48) | usati da `do_world` |

La stanza di un personaggio e' un **vnum** (`char_to_room(ch, vnum)`); l'indice di zona e' `real_roomp(vnum)->zone`.

## Mappatura comando -> funzioni del gioco

| Comando del protocollo | Funzioni/campi C | Modello nel gioco |
|---|---|---|
| `ping` | nessuna (`time(0)`) | |
| `info` | `Uptime`, `pulse`, contatore del modulo, `GetLagIndex()`, conteggio di `descriptor_list` per `connected`, `top_of_zone_table + 1`, `top_of_mobt`, `top_of_objt`, `VERSION` (`version.h`: `"1.7.0 cdrom"`) | `do_world` (`act.info.c` 4156) |
| `who` | scorre `character_list`; include `IS_PC(p) && !IS_LINKDEAD(p)` (e con `linkdead=true` anche i link morti); nome `GET_NAME`, livelli `player.level[i]` (`GetMaxLevel`, `multiclass.c` 296), `iClass`, `GET_RACE`, `GET_SEX`, `in_room`, `real_roomp(in_room)->zone`, `GET_POS`, `specials.fighting`, `specials.timer`, `invis_level` | `do_who` (`act.info.c` 2759): stesso ciclo su `character_list`, stesso filtro |
| `player.get` | ricerca per nome (sotto), lettura dei campi della tabella dei [campi modificabili](#campi-modificabili-live) | |
| `player.set` | ricerca, validazione, scrittura dei campi, `affect_total(ch)`, poi `do_save(ch, "", 0)` | `do_set` (`act.wizard.c` 2298): scrive gli stessi campi **senza validare nulla**; il canale valida |
| `zone.list` | `zone_table[0..top_of_zone_table]` | `do_world` |
| `zone.reset` | `reset_zone(i)` (`db.c` 2509) | `do_zload` (`act.wizard.c` 453-495) e `zone_update` (`db.c` 2404) |
| `load.mob` | `real_mobile` -> `read_mobile(nr, REAL)` (`db.c` 1591) -> `char_to_room(mob, room)` (`handler.c` 940) | `do_mload` (`act.wizard.c` 3376) |
| `load.obj` | `real_object` -> `read_object(nr, REAL)` (`db.c` 2294) -> `obj_to_room` o `obj_to_char` | `do_oload` (`act.wizard.c` 3424) |
| `player.inventory`, `obj.get` | `ch->equipment[]`, `ch->carrying`, `obj->contains`/`next_content`, `obj_index[].iVNum`; ref e impronta come sopra | `do_inventory`/`do_equipment` (`act.info.c`) |
| `obj.set` | scrittura dei campi con `unequip_char`/`reattach` per gli indossati, `proto_owns` + `free` per i testi, `do_save` | `ObjEdit` (`create.obj.c`) |
| `obj.remove` | `obj_from_obj` (se annidato) + `extract_obj`, `do_save` | `extract_obj` (`handler.c` 1799) |
| `echo` | `send_to_char(msg, ch)`, `send_to_room(msg, room)`, `send_to_all(msg)` (`comm.c` 1970/2155/1989) | |

### Trovare un giocatore per nome

Percorrere `descriptor_list` e prendere `p = d->original ? d->original : d->character` (come il commento in `do_who`), confronto del nome
senza maiuscole/minuscole (`strcasecmp` con `GET_NAME(p)`), **non** `get_char`/`get_char_vis` (cercano anche i mob e usano l'ordinale «2.nome»,
`handler.c` 1492). I link morti (`ch->desc == 0`) si trovano solo in `character_list`: sono visibili in `who`, **non** modificabili con `player.set`
(`player_not_playing`), perche' `save_char` richiede il descrittore (`db.c` 3182: se `!ch->desc` esce senza salvare) e perche' il
loro stato viene comunque salvato dal gioco quando scadono.

Condizioni per `player.set`/`load.* player`/`echo player`: `d->connected == CON_PLYNG`, `d->character != NULL`, `d->str == NULL`,
`d->showstr_point == NULL`, e per le scritture anche `d->original == NULL` (trasformati/switch: `player_busy`, perche' `do_save` ha un ramo
dedicato con scambio di equipaggiamento, `act.other.c` 318-360).

## Campi modificabili live

Tutti i campi hanno i nomi del DTO dei giocatori (gli stessi della modifica su file). Il canale applica i limiti del **tipo C** (come i
file) **e**, dove il gioco usa il valore come indice di tabella, quelli della tabella: il canale e' piu' severo dei file perche' il gioco e'
gia' in esecuzione e un valore errato non e' un file sbagliato ma un crash.

| Campo | C | Tipo | Intervallo live | Note |
|---|---|---|---|---|
| `gold` | `points.gold` | int | 0..2^31-1 | |
| `bankGold` | `points.bankgold` | int | 0..2^31-1 | |
| `exp` | `points.exp` | int | 0..2^31-1 | nessuna ricalcolo del livello (come `@ exp`) |
| `alignment` | `specials.alignment` | int | -1000..1000 | intervallo del commento di `structs.h`; **da verificare** che il gioco non lo ripulisca |
| `hit`, `mana`, `move` | `points.hit/mana/move` | `sh_int` | -32768..32767; **non oltre il massimo corrente** (`hit_limit` ecc.) | il gioco ripulisce nei tick (`limits.c`); portare sopra il massimo non ha senso |
| `spellsToLearn` | `specials.spells_to_learn` | `byte` | 0..127 | `byte` e' `char` con segno (`structs.h` 13): per questo 127, non 255 come nel file |
| `conditions.drunk/full/thirst` | `specials.conditions[DRUNK/FULL/THIRST]` | `sbyte` | -1..24 | -1 = non si ha bisogno (usato per gli dei); 24 e' il valore di partenza in `init_char` (`db.c` 3958, riga ~4214); **da verificare** il massimo |
| `str` | `abilities.str` (+ `affect_total`) | `sbyte` | **0..25** | `str_app[31]`, `dex_app[26]`, `con_app[26]`, `int_app[26]`, `wis_app[26]` (`constants.c` 3101-3342): oltre l'indice il gioco legge fuori tabella |
| `strAdd` | `abilities.str_add` | `sbyte` | 0..100 | indice di `str_app` via `STRENGTH_APPLY_INDEX` (`utils.h` 175) |
| `int`, `wis`, `dex`, `con`, `chr` | `abilities.intel/wis/dex/con/chr` | `sbyte` | **0..25** | `chr_apply[26]` (`constants.c` 3374) |
| `levels.<classe>` | `player.level[i]` | `byte` | 0..59; promozione a >= 51 solo con `confirm_immortal: true` | il gioco rifiuta di creare immortali ai non implementatori (`do_set` `lev`, 2454-2459: `LOW_IMMORTAL` = 51): il canale lo tratta come operazione pericolosa: una **promozione** (nuovo livello >= 51 e maggiore dell'attuale) e' rifiutata senza conferma esplicita e consentita con `confirm_immortal` (con avvertenza nella risposta e nell'audit); mantenere o abbassare un livello da immortale non richiede conferma; solo classi gia' possedute (`iClass`) |

**Non modificabili in v1** (il comando risponde `bad_params`):

- `maxHit`, `maxMana`, `maxMove`: in memoria includono equipaggiamento e incantesimi (`affect_modify` somma `APPLY_HIT` ecc. direttamente in
  `points.max_hit`); `char_to_store` li riporta al valore base togliendo l'equipaggiamento (`db.c` 3004), quindi un valore scritto «effettivo» salverebbe una base sbagliata;
- `armor`, `hitroll`, `damroll`, tiri salvezza: derivati (`affect_total`) e **forzati** nel file (`char_to_store` scrive `armor=100`, `hitroll=0`, `damroll=0`);
- `race`, `sex`, `classMask` (`iClass`), `played`, `birth`, `lastLogon`: strutturali o derivati;
- stringhe (`title`, `description`, alias, `poofin`...): sono puntatori allocati con `CREATE`/`strdup` e liberati da `free_char`: scrivere stringhe significa gestire memoria del gioco; rimandato;
- flag (`act`, `affectedBy`, `userFlags`), `startRoom`/`loadRoom`, abilita' (`skills[]`), effetti (`affected`), inventario ed equipaggiamento: rimandati (l'inventario si arricchisce con `load.obj player`);
- password (`d->pwd`, `char_file_u.pwd`): mai, in nessuna forma.

Dopo la scrittura degli attributi base il modulo chiama `affect_total(ch)` (`handler.c` 628), che ricalcola `tmpabilities` da `abilities`, equipaggiamento e
incantesimi; `do_set` invece scrive anche `tmpabilities`, ma e' meno corretto con oggetti che modificano le abilita'.

## Salvare: `save_char` e rent

`save_char(ch, load_room)` (`db.c` 3182) scrive **solo** il record `lib/players/<nome>.dat` (con `EMANUELE`: apre `r+b` e riscrive
3036 byte; `fwrite` non atomico). Non scrive il rent. `char_to_store` (`db.c` 3004) ha effetti collaterali sul personaggio: toglie e rimette
l'equipaggiamento, aggiorna `played` e `last_logon`, azzera `charging`.

Il comando `save` del giocatore e' `do_save` (`act.other.c` 290), che fa nell'ordine `recep_offer` -> `save_obj` (scrive `lib/rent/<nome>`)
-> `save_char(ch, AUTO_RENT)` (e per i trasformati anche `write_char_extra`, `WriteCharQuest`). `close_socket` lo usa alla disconnessione
(`comm.c` 1754-1860). Percio' **`save: true` di `player.set` DEVE chiamare `do_save(ch, "", 0)`**, non `save_char` da solo: cosi' record e rent
restano coerenti con cio' che il giocatore stesso otterrebbe e la procedura e' quella gia' esercitata dal gioco. `AUTO_RENT` (-2) significa «ricomincia dal rent automatico»: il
giocatore riparte da dove era. `NO_RENT_COST` e' definito: il rent non addebita nulla.

`save_all()` (`comm.c` 1980) e' un'altra via per salvare tutti, ma qui non serve.

## Dettagli per comando

**`zone.reset`**

- `reset_zone(i)` esegue la tabella `zone_table[i].cmd` con i limiti normali (`mob_index[...].number < max`, `!fighting_in_room`, `CheckKillFile`) e a fine corsa
  pone `age = 0` e `start = 1`. **Non rimuove** nulla.
- **Eccezione per la zona 0**: alla prima chiamata `reset_zone(0)` non esegue il reset ma legge i file di «scratch» `world/mobs.N` e ritorna
  (`db.c` 2526-2545). Il canale rifiuta l'indice 0 con `forbidden_by_policy`.
- `zone_update` accoda le zone da resettare in `gReset_q` ponendo `age = ZO_DEAD (999)` (`db.c` 2404); se si resetta a mano una zona in coda,
  il reset automatico la rifara' subito dopo: il modulo deve togliere la voce dalla coda (scorrere `gReset_q.head` e unire la lista, 8-10 righe)
  oppure accettare il doppio reset. Preferita la rimozione; **da verificare** in prova.
- `only_if_empty` usa `is_empty(zone)` (`db.c` 2788): controlla `real_roomp(i->character->in_room)->zone` per ogni descrittore con `connected == 0`.
- La zona di un editor e' un **indice di posizione** che puo' non coincidere con quello del gioco (il gioco ne vede 90, l'adapter 93, vedi
  [limiti noti](dikumod.md#limiti-noti)): per questo il protocollo ha `zone.list` e accetta `room`. L'editor DEVE passare per `zone.list`/`room`, mai
  l'id dell'adapter come indice.
- `char_to_room` fa il reset iniziale di una zona mai inizializzata (`start == 0`) quando entra un giocatore (`handler.c` 940-1003); il canale non lo altera.

**`load.mob`** — `read_mobile(vnum, VIRTUAL)` fa gia' `real_mobile` e logga l'errore se il vnum non esiste (`mudlog`); il modulo controlla
prima (`real_mobile(vnum) >= 0`) per rispondere `not_found` e non scrivere nel log del gioco. Una volta creato incrementa `mob_index[nr].number` (`db.c` 2062).
Poi `char_to_room(mob, room)`; `room` va controllata con `real_roomp(room) != NULL` (altrimenti `char_to_room` mette il mob in stanza 0). Il mob creato col canale non ha
`specials.zone` ne' `lStartRoom` impostati come dal reset (`reset_zone` li imposta per `ACT_SENTINEL`): un mob sentinella creato cosi' puo' comportarsi diversamente
(**da verificare**).

**`load.obj`** — come `do_oload`: `read_object(vnum, VIRTUAL)` poi `obj_to_char` / `obj_to_room`. `do_oload` rifiuta alcuni vnum a mano (`act.wizard.c` ~3480-3510: 1600, 5311, 13702,
21113, 21117, 21120-21122, reindirizza 15809 a 15861, e blocca 150-199 a chi non e' il proprietario del progetto): la deny-list del canale parte da
questi valori ed e' configurabile. `read_object` ritorna NULL per un vnum inesistente: controllare.

**`echo`** — `send_to_char`/`send_to_room`/`send_to_all` passano il testo da `ParseAnsiColors` (`comm.c` 190), che scrive in un buffer **statico** di
`MAX_STRING_LENGTH` (20480) **senza** controllare la lunghezza e interpreta `$c` + 4 cifre come colore: il modulo limita `text` a 400 byte e sostituisce ogni `$` con `\$`
(la sequenza `\$` e' riconosciuta e diventa `$`, `comm.c` 200-204). Il testo deve terminare con `\n\r`. `send_to_room` non controlla che la stanza
esista (`real_roomp(room)->people`, `comm.c` 2155): il modulo controlla prima. `send_to_all` raggiunge solo i descrittori con `connected == 0`.
**Da verificare**: `ParseAnsiColors` con `SYS_NOANSI` impostato (`ansi_parse` ritorna NULL e c'e' un `strcat(buf, NULL)`): con l'opzione `-A` del server il gioco puo' gia' cadere con un
`$c` nel testo; il modulo, eliminando `$`, non entra in quel ramo.

**Log** — `mudlog` (`utility.c` 656) formatta in un buffer `LARGE_BUFSIZE` con una stringa di formato: va sempre chiamato con `"%s"` e un testo troncato; l'audit del modulo e' un file proprio.

## Insidie

1. **Liste in iterazione.** Il modulo gira fuori dai cicli del gioco, ma i suoi stessi comandi non devono modificare una lista mentre la percorrono:
   `zone.reset` e `load.*` allungano `character_list` e `rp->people`; nessun comando del canale chiama `extract_char`/`close_socket`.
   `next_to_process` (variabile globale di `comm.c`, riga 59) e' ricalcolato a ogni iterazione e `close_socket` lo aggiusta (riga 1828): non va toccato.
2. **Puntatori che non vivono tra due iterazioni.** Il canale NON conserva `struct char_data *` tra una richiesta e l'altra: a ogni richiesta ricerca per nome. Il giocatore
   puo' essere uscito, trasformato, morto o ricaricato dopo l'ultima richiesta. Il gioco ha `nMagicNumber`/`CHAR_VALID_MAGIC` (`structs.h` 1238) per rilevare strutture liberate: controllarlo dopo la ricerca.
3. **Stato di combattimento.** Cambiare `hit` a un giocatore in combattimento e' consentito (come `@ hit`), ma `hit <= 0` fuori dai controlli di morte
   (`update_pos` in `fight.c`) lascia il giocatore in posizione incoerente fino al tick successivo; il modulo vieta `hit < 1` in `player.set` v1 e non chiama `damage()`.
   `zone.reset` non esegue `M` in stanze con combattimenti (`fighting_in_room`).
4. **Messaggi.** Le modifiche non avvisano il giocatore: nessun `act()` dal canale (tranne `notify`). I messaggi sono in latin-1 e in italiano; la tabella dei messaggi sta nel modulo.
5. **Salvataggio e rent**: `do_save` ha un ramo per trasformati/switch (esclusi con `player_busy`) e scrive due file in modo non atomico; con il disco pieno o un
   file bloccato il salvataggio puo' fallire senza che `do_save` lo segnali (ritorna `void`): la risposta `saved: true` significa «`do_save` e' stato chiamato», non «verificato»;
   per verificarlo si puo' confrontare `mtime` di `players/<nome>.dat` prima e dopo (**da verificare**).
6. **Descrittori ereditati.** `system()` in `interpreter.c` e `db.c`: i descrittori del canale con `FD_CLOEXEC` (previsto dal protocollo).
7. **Fuori memoria / limiti**: il gioco usa `CREATE` (alloc con `assert`) senza gestione dell'errore: `load.mob`/`load.obj` limitano `count` a 10 e le richieste sono limitate in frequenza.
8. **Buffer di uscita dei giocatori**: `write_to_output` (`comm.c` 1127) entra in overflow se la coda di un giocatore supera `LARGE_BUFSIZE` (poi ignora i messaggi): `echo all` a raffica puo' mandare
   in overflow i giocatori lenti. Il limite di richieste al secondo del protocollo limita il danno.
9. **Check del gioco** `CheckObjectExDesc`/`CheckCharAffected` (comm.c 100-160) girano attorno ai comandi dei giocatori: segnalano strutture corrotte nel log. Il modulo non li chiama; dopo `player.set` e' opportuno eseguirli in fase di prova.
10. **Orari di reboot automatici** (`check_reboot`, `modify.c` 1089) e `mudshutdown`: a gioco in chiusura il poll non gira piu'; i client ricevono EOF. L'editor tratta la chiusura come `unreachable`.

## Configurazione del modulo

Solo **variabili d'ambiente** lette da `livectl_init` (il token e' un segreto, le altre seguono lo stesso canale per semplicita'):

| Variabile | Default | Significato |
|---|---|---|
| `LIVECTL_SOCKET` | (nessuno) | percorso **assoluto** del socket Unix; senza, il modulo non si attiva |
| `LIVECTL_TOKEN` | (nessuno) | segreto, almeno 32 caratteri; cancellato dall'ambiente dopo la lettura |
| `LIVECTL_CLASSES` | `read` | `read` oppure `read,write` (le scritture sono disattivate di default) |
| `LIVECTL_MAX_CONN` | `4` | connessioni massime (1..16) |
| `LIVECTL_AUDIT` | `livectl.audit` | file di audit (relativo a `lib/` o assoluto) |
| `LIVECTL_DENY_OBJ` | `150-199,1600,5311,13702,21113,21117,21120-21122` | vnum non creabili da `load.obj` (deny-list di `do_oload`) |

Interruttore di emergenza: se nella cartella dati esiste il file `livectl.disable` il modulo non si attiva. Il modulo e' compilato solo con `-DLIVECTL`; senza il
flag `livectl_init`/`livectl_poll` sono vuote e una build e' identica a oggi. Codice, patch e istruzioni: `adapters/dikumod/mud-module/` (README).
Sorgente di riferimento: solo **DikuMod1** (`/dati/luca/muds/leu`); le altre varianti non sono considerate.

## Inventario e oggetti istanza

Feature `inventory` ([comandi](../backend/live-control-protocol.md#riferimenti-agli-oggetti)): `player.inventory`, `obj.get`, `obj.set`, `obj.remove`. Sorgente: `struct obj_data` (`structs.h` 526), `struct obj_flag_data` (505), `handler.c`, `db.c`, `reception.c`.

### Dove stanno gli oggetti

| Cosa | Dove |
|---|---|
| inventario | `ch->carrying`, lista concatenata con `next_content` (l'oggetto nuovo entra **in testa**: gli indici scalano) |
| equipaggiamento | `ch->equipment[0..MAX_WEAR-1]` (`MAX_WEAR` = 23, `WEAR_BODY` = 5, `WEAR_BACK` = 18), con `obj->equipped_by` e `obj->eq_pos` |
| contenuto | `obj->contains` (testa) e `next_content`, con `obj->in_obj` al contrario; il peso di un contenitore **include** il contenuto (`obj_to_obj` somma il peso all'intera catena di contenitori e a `carry_weight` di chi li porta) |
| vnum | `obj_index[obj->item_number].iVNum` (`item_number` = -1 per gli oggetti creati dal codice, es. la bacca di `magic3.c`) |

I ref `eq:<slot>` e `inv:<i>[/<j>...]` si risolvono scorrendo queste liste a ogni richiesta (limite di 100000 passi e 8 livelli). Nessun puntatore sopravvive fra due richieste.

### Impronta (`fp`)

FNV-1a a 32 bit sulla sequenza: vnum, `type_flag`, `name`, `short_description`, `description` (con il terminatore), `extra_flags`, i quattro `value`, e per ognuno dei 5 affect `location` e `modifier`.
Peso e `timer` sono esclusi di proposito. Si ricalcola a ogni risoluzione e si confronta con `expect.fp` insieme al vnum; la risposta di `obj.set` ne riporta il nuovo valore.

### Testi di un oggetto istanza

Come il gioco gestisce `name`, `short_description`, `description`, `action_description`:

- `read_object` (`db.c` 2294) crea l'istanza con `CREATE` + `clear_object`, poi o legge i testi dal file (`fread_string`, `malloc`) o li **duplica** dal prototipo in memoria con `clone_obj_to_obj` (`db.c` 2083: un `strdup` per testo).
  Anche il caricamento dal rent (`reception.c` 359, 1414) usa `malloc`. Nessun percorso del sorgente fa puntare un'istanza ai testi di `obj_index[]` (`name`, `short_desc`, `long_desc` dell'indice o `data`): grep di tutte le assegnazioni a `->name`, `short_description`, `description` nei `.c`.
- `free_obj` (`db.c` 3502, ramo `EMANUELE`) fa `free()` di ognuno; `extract_obj` (`handler.c` 1799) lo chiama in coda. L'editor di oggetti in-gioco (`create.obj.c` 380-460) fa gia' `free(vecchio); nuovo = strdup(arg)`.

**Regola del modulo**: allocare con `strdup` la nuova stringa **prima** di toccare l'oggetto (se l'allocazione fallisse non si e' modificato nulla), poi assegnare il puntatore e liberare il vecchio con `free()` **solo se non e' di proprieta' del prototipo**
(`proto_owns`: uguale a `obj_index[nr].name`, `.short_desc`, `.long_desc`, oppure a `name`/`short_description`/`description`/`action_description` della copia `obj_index[nr].data`). Con il sorgente attuale la condizione non scatta mai, e' una difesa contro modifiche future o strutture create altrove:
liberare un testo del prototipo corromperebbe tutti gli oggetti di quel vnum e farebbe un `free()` invalido alla loro distruzione. Un puntatore `NULL` si sostituisce senza liberare. Verificato dal vivo: cambiare i testi di un'istanza non cambia una seconda istanza dello stesso vnum creata dopo,
e distruggere l'istanza modificata non fa cadere il gioco.

**Lunghezze**: `put_obj_in_store` (`reception.c` 556) copia con `strcpy` in `obj_file_elem.name[128]`, `sd[128]`, `desc[256]` **senza** controllo: ogni testo piu' lungo di 127/127/255 byte sovrascrive il record successivo (e, nello stack di `do_save`, la memoria vicina).
Il modulo rifiuta quindi `name` e `short_description` oltre 127 byte e `description` oltre 255. Rifiuta anche `$` (il testo passa da `ParseAnsiColors`/`act`), `~` e i caratteri di controllo.

### Campi e rent

| Campo del protocollo | C | Persiste nel rent? |
|---|---|---|
| `name`, `short_description`, `description` | `name`, `short_description`, `description` | si' (`oe->name/sd/desc`) |
| `values[0..3]` | `obj_flags.value[]` | si' |
| `weight` | `obj_flags.weight` | si' |
| `extra_flags` | `obj_flags.extra_flags` (`unsigned long`) | si' (come `int`) |
| `timer` | `obj_flags.timer` (`OBJ_NOTIMER` = -7000000; un timer negativo diverso da `OBJ_NOTIMER` fa buttare l'oggetto al salvataggio, per questo il minimo e' 0) | si' |
| `affects[0..4]` | `affected[].location` (`short`), `.modifier` (`int32_t`) | si' |
| `cost`, `cost_per_day`, `wear_flags`, `type_flag` | `obj_flags` | no: tornano quelli del prototipo; sola lettura |

`location` ammesso 0..64 (`APPLY_NONE`..`APPLY_T_MANA`, `structs.h` 823-891; `affect_modify` segnala `default` per i valori ignoti). `bitvector` (bit di `affected_by` dati dall'oggetto) e' leggibile, non modificabile.

### Oggetto indossato e pesi

- `unequip_char` (`handler.c` 1281) toglie `affect_modify(..., FALSE)` di ogni affect, ricalcola `affect_total` e sottrae il peso (`NO_PESO_ON_BACK`: tranne in `WEAR_BACK`); `equip_char` (1134) fa il contrario **dopo** controlli che possono buttare l'oggetto a terra
  (`CheckEgoEquip`, `CheckGetBarbarianOK`, `ItemAlignClash` + `do_save`). Il modulo, per un oggetto (o un contenitore) indossato, chiama `unequip_char`, applica la patch e ripete **solo la coda** di `equip_char` (`reattach`: slot, `equipped_by`/`eq_pos`, correzione AC per le armature, `affect_modify(..., TRUE)`,
  `affect_total`, peso). Cosi' i bonus (massimo di punti vita, tiri salvezza, ...) restano coerenti e un cambio di `extra_flags` non puo' far cadere l'oggetto.
- **Peso**: delta = nuovo - vecchio; si aggiunge all'oggetto, a ogni contenitore antenato (minimo 0) e, se la radice e' portata (non indossata), a `IS_CARRYING_W(ch)` (minimo 0); se la radice e' indossata il peso rientra con `reattach`. Verificato dal vivo per oggetto sciolto, annidato e indossato.
- **`obj.remove`**: un oggetto annidato passa prima da `obj_from_obj` (aggiorna i pesi dei contenitori e di `carry_weight`), poi `extract_obj` (che per un contenitore estrae ricorsivamente il contenuto, per un indossato chiama `unequip_char`, per uno portato `obj_from_char`).
  `obj_from_obj` ha un `assert` se l'oggetto risulta contemporaneamente annidato e portato/indossato (`object_list_new_owner` imposta `carried_by` sugli annidati; `obj_from_char` in quel caso si limita a loggare): il modulo controlla e risponde `internal` invece di arrivare all'`assert`.

### `load.obj` e vnum alti

`read_object(vnum, VIRTUAL)` accetta qualunque vnum; il rent salva `item_number` come `short` (`obj_file_elem`, `put_obj_in_store`): con vnum > 32767 il salvataggio scrive un numero diverso e al login l'oggetto cambia identita' o viene saltato. `load.obj` a un giocatore con `vnum` > 32767 risponde con `warnings: ["vnum_not_saveable"]`.
Nei dati reali esistono oggetti con vnum 35000 e 35001.

### Da verificare (inventario)

- Il peso di un oggetto annidato in un contenitore **indossato**: `obj_to_obj` non somma a `carry_weight` per i contenitori indossati ma `unequip_char` sottrae il peso cumulativo; il gioco stesso ha questa asimmetria, il modulo applica il delta solo se la radice e' portata e lascia a `reattach` il caso indossato (non provato con un contenitore indossato).
- `GiveMinStrToWield` (solo PNG) non e' replicato in `reattach`.
- Oggetti con `item_number` -1 (creati dal codice) non hanno vnum (`null` nel protocollo): letti e modificati come gli altri, non provati dal vivo.
- Il `timer` scala da solo nel gioco; la lettura subito dopo la scrittura puo' differire di poco.
- Nessuna modifica di `action_description` ne' delle descrizioni extra (`ex_description`).

## Righe effettive

| Parte | Righe |
|---|---|
| `livectl_json.c` / `.h`: parser e serializzatore JSON a limiti fissi | ~540 |
| `livectl.c`: socket, framing, limiti, token, classi, audit, i 14 comandi, configurazione | ~2400 |
| `livectl.h`, harness di fuzz (`fuzz/fuzz_json.c`) | ~110 |
| modifiche ai file originali (`leu-livectl.patch`) | 12 righe in `comm.c` (include, `livectl_init();`, `livectl_poll();`), 2 nel `Makefile` (`$(LIVECTL_FLAGS)` e due oggetti) |

La stima iniziale (1100-1500 righe) era ottimistica: gran parte del peso e' nella validazione dei parametri e nei messaggi d'errore stabili.
Per l'editor (Python, a parte): client asincrono, adapter `LiveAdapter` + rotte + DTO, comandi CLI: non ancora scritti. Esistono invece il finto
server (`tests/support/live_fake_server.py`) e la suite di conformita' (`tests/live/`).

## Costruire e provare

Il modulo non modifica i sorgenti originali: si lavora su una **copia**.

```bash
M=/percorso/pachimudeditor/adapters/dikumod/mud-module
mkdir /tmp/mud && cp -r /dati/luca/muds/leu/. /tmp/mud/ && cd /tmp/mud && rm -rf bin .depend src/*.o   # copia della radice di leu
git apply $M/leu-livectl.patch                 # solo se src/livectl.c manca: Makefile (2 righe) e src/comm.c (12 righe)
cp $M/livectl*.[ch] src/
make LIVECTL_FLAGS=-DLIVECTL                   # Makefile reale del gioco (nella radice), g++ -std=gnu++98 -> bin/leu
LIVECTL_SOCKET=/tmp/mud/l.sock LIVECTL_TOKEN=$(openssl rand -hex 32) LIVECTL_CLASSES=read,write bin/leu -d lib 4000
```

Dettagli, variabili e istruzioni esatte: `adapters/dikumod/mud-module/README.md`. Prova automatica: `uv run pytest tests/live` (default: la cartella `leu`; altrimenti `DIKUMOD_SRC=<radice> DIKUMOD_LIB=<lib>`)
(costruisce il gioco su copie in `/tmp`, crea il giocatore `Tester`, lo fa entrare e lancia la stessa suite di conformita' del finto server).

**Verificato davvero** (copia della radice di `leu` con i dati reali copiati in una cartella temporanea): compilazione con il Makefile reale (`-std=gnu++98`, senza errori) sia
con sia senza `-DLIVECTL`, avvio del gioco con il canale, login di un giocatore, tutti i comandi della v1 contro il gioco vivo (modifica con salvataggio su
`players/tester.dat`, reset di zona, creazione di mob e oggetti, messaggi, deny-list, limiti, raffiche, input spazzatura) e fuzz del parser con ASan/UBSan.

## Da verificare

- I limiti di `alignment` (-1000..1000) e `conditions` (-1..24) sono scelti dal modulo: il gioco non li impone in `do_set`.
- Mob sentinella creati con `load.mob` (`lStartRoom` non impostato come dal reset di zona).
- `saved: true` significa che `do_save` e' stato chiamato e che `mtime` di `players/<nome>.dat` e' avanzato (risoluzione di un secondo): non e' una verifica del contenuto.
- Comportamento con `-A` (`SYS_NOANSI`) e `$c` nei testi: il modulo elimina il `$`, ma il percorso `ansi_parse` del gioco non e' stato esercitato.
- Giocatori trasformati (`polymorph`) e link morti: la logica c'e' (`who` li elenca, le scritture rispondono `player_busy`/`player_not_playing`) ma non e' stata provata dal vivo.
- Fuzz solo del parser: il resto del modulo (socket, comandi) e' provato dalla suite di conformita' e dal test con input spazzatura, non con un fuzzer.
- basedmud/ROM: hook equivalenti non ancora cercati.
