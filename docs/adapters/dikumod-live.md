# Diku Modificato: profilo del canale live

**Stato: specifica, non implementata.** Applica il [protocollo `livectl`](../backend/live-control-protocol.md) a Diku Modificato: dove si
aggancia il modulo C nel sorgente, quali funzioni del gioco usano i comandi, quali campi si possono cambiare a gioco acceso e quali
insidie ci sono. Il protocollo (trasporto, sicurezza, comandi, errori) e' in [canale di controllo live](../backend/live-control-protocol.md);
qui c'e' solo cio' che dipende dal sorgente.

Tutto quello che segue e' stato letto nel sorgente indicato; dove non e' stato possibile verificare e' scritto **da verificare**.
I numeri di riga sono di DikuMod1 (`/dati/luca/muds/oldlinux/DikuMod1/src`) e possono scorrere.

## Sorgenti esaminati

| Albero | Contenuto | Uso in questo profilo |
|---|---|---|
| `oldlinux/DikuMod1/src` | sorgenti completi (57 file `.c`, ~97 000 righe), porting x86_64 con g++ | riferimento (`DikuMod`/«dikumod») |
| `oldlinux.save/leu/src` | identico a DikuMod1 (verificato con `diff -rq`, esclusi i `.o`) | nessuno in piu' |
| `oldlinux/DikuMod2/src`, `dikumod-root/dikumod2/src` | **solo 4 file** (`act.wizard.c`, `comm.c`, `db.c`, `spec_assign.c`); il binario `leu` e' un a.out i386 del 2004 | confronto con DikuMod1 |

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
| `levels.<classe>` | `player.level[i]` | `byte` | 0..50, oltre solo se il MUD lo consente | il gioco rifiuta di creare immortali ai non implementatori (`do_set` `lev`, 2454-2459: livelli > 50 e `LOW_IMMORTAL` = 51): il canale ripete il divieto (`forbidden_by_policy`) |

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

## Differenze dikumod / dikumod2

| Aspetto | DikuMod1 | DikuMod2 |
|---|---|---|
| Sorgenti disponibili | completi | **solo 4 file**; il resto **da verificare** (si presume uguale a DikuMod1) |
| `comm.c` | `room_db` array (`extern struct room_data *room_db[WORLD_SIZE]`), `MAX_BAN_HOSTS` con `<` | `room_db` puntatore, ciclo con `<=` (fuori di uno, solo con `SITELOCK`); stesse funzioni e stessi punti di innesto (il confronto di `comm.c` mostra solo queste differenze e il nome del proprietario `Benem`/`Fiko`) |
| `db.c` | `closedir(dir)` dopo ogni `opendir` (5 punti); `update_obj_file()` al boot solo con `BOOT_UPDATE_OBJ_FILE`; `store_to_char`/`char_to_store` copiano `affected` campo per campo | `closedir` **mancante** nei 5 punti: ogni lettura di cartella (`players`, `zones`, `rooms`, ...) perde un descrittore; `store_to_char` usa `affect_to_char(ch, &st->affected[i])` e `char_to_store` copia la struttura intera (incluso il puntatore `next`; effetti **da verificare**); `update_obj_file()` al boot e' **sempre** eseguita (manca l'`#ifdef`; con dati vecchi puo' azzerare il rent) |
| `act.wizard.c` | | differisce solo per il nome del proprietario (`Fiko`) nelle eccezioni dei comandi degli immortali |
| Binario disponibile | ricompilabile (porting x86_64) | solo `leu` a.out i386 del 2004: **non** patchabile senza i sorgenti completi |

Conseguenze: lo **stesso modulo** funziona per entrambi (le funzioni usate sono quelle di `db.c`, `handler.c`, `comm.c`, `act.*`), ma per dikumod2 va prima
ricostruita una build dai sorgenti completi (DikuMod1 + i 4 file di DikuMod2) e provata. La perdita di descrittori di DikuMod2 e' un problema preesistente che pesa di piu'
con un canale che apre descrittori propri (da correggere o da monitorare). Nessuna differenza nei campi del giocatore: lo stesso `char_file_u` da 3036 byte
(il [formato](../formats/dikumod.md#9-file-giocatore-e-rent) vale per entrambi).

## Configurazione del modulo

Un file `livectl.conf` nella cartella dati (`lib/`), letto da `livectl_init` con un parser a righe `chiave = valore`, **senza** il token. Chiavi:
`socket` (percorso assoluto), `token_file` (percorso assoluto, `0600`), `classes` (default `read`; `read,write` abilita le scritture), `max_connections`,
`allow_uid`, `audit_file`, `deny_obj` (elenco di vnum), `allow_immortal_levels` (default `0`), `enabled` (default `0`). Il modulo e' compilato solo con `-DLIVECTL`
(file `livectl.c` aggiunto a `OBJS` nel `Makefile` e, senza il flag, la funzione e' vuota): una build senza il flag e' identica a oggi.

## Stima delle righe

| Parte | Righe (C, stile del sorgente) |
|---|---|
| parser/serializzatore JSON rigoroso (a limiti fissi, in-place) | 250-350 |
| socket, accept, buffer per connessione, framing, limiti, token bucket | 250-350 |
| autenticazione, token (confronto a tempo costante), classi/allowlist, audit | 150-200 |
| comandi (`ping`, `info`, `who`, `zone.*`, `player.*`, `load.*`, `echo`) | 350-450 |
| configurazione, conversione latin-1/UTF-8, tabelle (nomi di classi, razze, posizioni) | 100-150 |
| **Totale nuovo** (`livectl.c`, eventualmente `livectl_json.c`) | **~1100-1500** |
| modifiche ai file esistenti | ~12: `comm.c` (+4: `livectl_init();` dopo `boot_db`, `livectl_poll();` in `game_loop`, dichiarazioni in `protos.h` o locali), `Makefile` (+1 oggetto), `protos.h` (+3) |

Per l'editor (Python, a parte): client asincrono ~250 righe, adapter `LiveAdapter` + rotte + DTO ~400, test con un finto server del protocollo ~300.

## Da verificare

- Il comportamento effettivo dei limiti di `alignment` e `conditions` (il gioco non li impone in `do_set`).
- Rimozione della voce da `gReset_q` dopo un `zone.reset` manuale, in prova su una copia.
- Mob sentinella creati con `load.mob` (`lStartRoom`).
- Verifica del salvataggio (`mtime`).
- Sorgenti completi di DikuMod2 e riproducibilita' della sua build.
- basedmud/ROM: hook equivalenti non ancora cercati.
- Compilazione del modulo con il `Makefile` reale (`-std=gnu++98`) e prova di fuzzing del parser JSON.
